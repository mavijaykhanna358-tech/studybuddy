import importlib.util
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import (
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from project.settings import BASE_DIR


SETTINGS_PATH = BASE_DIR / 'project' / 'settings.py'

STRONG_SECRET_KEY = 'unit-test-secret-key-that-is-long-enough-to-pass-checks-0123456789'

CONSOLE_BACKEND = 'django.core.mail.backends.console.EmailBackend'


def load_settings(**environment):
    """
    Execute `project/settings.py` again with `environment` applied
    and return the fresh module.

    A key mapped to `None` is removed from the environment first, so
    a test can assert on the fallback that is used when the variable
    is absent.

    The module is deliberately not registered in `sys.modules`, so
    reloading it cannot disturb the settings Django already built
    for the running test process.
    """
    overrides = {
        key: value
        for key, value in environment.items()
        if value is not None
    }

    removals = [
        key
        for key, value in environment.items()
        if value is None
    ]

    spec = importlib.util.spec_from_file_location(
        'settings_probe',
        SETTINGS_PATH,
    )

    module = importlib.util.module_from_spec(spec)

    with mock.patch.dict(os.environ, overrides):

        for key in removals:
            os.environ.pop(key, None)

        spec.loader.exec_module(module)

    return module


class EmailSettingsTest(SimpleTestCase):
    def test_resend_is_used_when_an_api_key_is_present(self):
        settings = load_settings(
            DJANGO_ENV='production',
            SECRET_KEY=STRONG_SECRET_KEY,
            RESEND_API_KEY='re_test_key',
        )

        self.assertEqual(
            settings.EMAIL_BACKEND,
            'users.email_backend.ResendEmailBackend',
        )

    def test_console_backend_is_the_fallback_without_an_api_key(self):
        settings = load_settings(
            DJANGO_ENV='production',
            SECRET_KEY=STRONG_SECRET_KEY,
            RESEND_API_KEY=None,
        )

        self.assertEqual(
            settings.EMAIL_BACKEND,
            CONSOLE_BACKEND,
        )

    def test_explicit_email_backend_wins(self):
        settings = load_settings(
            DJANGO_ENV='production',
            SECRET_KEY=STRONG_SECRET_KEY,
            RESEND_API_KEY='re_test_key',
            EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        )

        self.assertEqual(
            settings.EMAIL_BACKEND,
            'django.core.mail.backends.locmem.EmailBackend',
        )


class DebugSettingsTest(SimpleTestCase):
    def test_debug_is_on_by_default_for_development(self):
        settings = load_settings(
            DJANGO_ENV='development',
            DEBUG=None,
        )

        self.assertTrue(settings.DEBUG)

    def test_debug_is_off_by_default_for_production(self):
        settings = load_settings(
            DJANGO_ENV='production',
            DEBUG=None,
            SECRET_KEY=STRONG_SECRET_KEY,
        )

        self.assertFalse(settings.DEBUG)

    def test_debug_can_be_forced_on_for_a_production_env(self):
        settings = load_settings(
            DJANGO_ENV='production',
            DEBUG='True',
            SECRET_KEY=STRONG_SECRET_KEY,
        )

        self.assertTrue(settings.DEBUG)

    def test_debug_can_be_forced_off_for_a_development_env(self):
        settings = load_settings(
            DJANGO_ENV='development',
            DEBUG='False',
            SECRET_KEY=STRONG_SECRET_KEY,
        )

        self.assertFalse(settings.DEBUG)


class ProductionSecretsTest(SimpleTestCase):
    def test_weak_secret_key_is_rejected_when_debug_is_off(self):
        with self.assertRaises(ImproperlyConfigured):
            load_settings(
                DJANGO_ENV='production',
                DEBUG=None,
                SECRET_KEY='insecure',
            )

    def test_weak_secret_key_is_allowed_while_debug_is_on(self):
        settings = load_settings(
            DJANGO_ENV='development',
            DEBUG=None,
            SECRET_KEY='insecure',
        )

        self.assertTrue(settings.DEBUG)


class AuthFlowTest(TestCase):
    def test_root_redirects_to_login_for_anonymous_user(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))

    def test_registration_redirects_to_login(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newauthuser',
                'email': 'newauthuser@example.com',
                'password1': 'Strongpass123!',
                'password2': 'Strongpass123!',
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))

    def test_logout_redirects_to_login(self):
        user = get_user_model().objects.create_user(
            username='logoutuser',
            email='logout@example.com',
            password='Pass123!'
        )
        self.client.force_login(user)

        response = self.client.post(reverse('logout'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))


class ProfileViewTest(TestCase):
    def test_profile_requires_login(self):
        response = self.client.get(
            reverse('profile')
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_profile_renders_for_a_signed_in_user(self):
        user = get_user_model().objects.create_user(
            username='profileuser',
            email='profile@example.com',
            password='Pass123!'
        )

        self.client.force_login(user)

        response = self.client.get(
            reverse('profile')
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'profileuser')


class PasswordResetEmailTest(TestCase):
    def test_reset_email_link_uses_the_configured_domain(self):
        # The link must point at the public site rather than the
        # host the request happened to arrive on, otherwise a reset
        # sent through an alternate hostname is a dead link.

        get_user_model().objects.create_user(
            username='mailuser',
            email='mailuser@example.com',
            password='Pass123!'
        )

        with override_settings(
            EMAIL_BACKEND=(
                'django.core.mail.backends.locmem.EmailBackend'
            ),
            FRONTEND_BASE_URL=(
                'https://studybuddyapp.in.net'
            ),
        ):

            self.client.post(
                reverse('password_reset'),
                {
                    'email': 'mailuser@example.com',
                }
            )

        self.assertEqual(len(mail.outbox), 1)

        body = mail.outbox[0].body

        self.assertIn(
            'https://studybuddyapp.in.net/reset/',
            body
        )

        self.assertNotIn('testserver', body)

    def test_unknown_email_does_not_reveal_whether_the_account_exists(self):
        response = self.client.post(
            reverse('password_reset'),
            {
                'email': 'nobody@example.com',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_an_invalid_link_explains_itself_instead_of_erroring(self):
        # Regression test: the confirm template used to call
        # `as_widget(attrs={'class': ...})`, which the template
        # language cannot parse, so this page raised a
        # TemplateSyntaxError instead of rendering.

        user = get_user_model().objects.create_user(
            username='badtoken',
            email='badtoken@example.com',
            password='Pass123!'
        )

        uid = urlsafe_base64_encode(
            force_bytes(user.pk)
        )

        response = self.client.get(
            reverse(
                'password_reset_confirm',
                kwargs={
                    'uidb64': uid,
                    'token': 'not-a-real-token',
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'invalid or has already been'
        )

    def test_a_valid_link_renders_a_styled_form(self):
        user = get_user_model().objects.create_user(
            username='goodtoken',
            email='goodtoken@example.com',
            password='Pass123!'
        )

        uid = urlsafe_base64_encode(
            force_bytes(user.pk)
        )

        token = default_token_generator.make_token(user)

        response = self.client.get(
            reverse(
                'password_reset_confirm',
                kwargs={
                    'uidb64': uid,
                    'token': token,
                },
            ),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'class="sb-input"'
        )
        self.assertContains(
            response,
            'csrfmiddlewaretoken'
        )


class RegistrationValidationTest(TestCase):
    def test_duplicate_username_shows_error_and_does_not_create_user(self):
        get_user_model().objects.create_user(
            username='takenuser',
            email='first@example.com',
            password='Strongpass123!'
        )

        response = self.client.post(
            reverse('register'),
            {
                'username': 'takenuser',
                'email': 'second@example.com',
                'password1': 'Strongpass123!',
                'password2': 'Strongpass123!',
            },
            follow=True,
        )

        self.assertContains(response, 'already taken', status_code=200)
        self.assertEqual(get_user_model().objects.filter(username='takenuser').count(), 1)

    def test_password_mismatch_shows_error(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newuser',
                'email': 'newuser@example.com',
                'password1': 'Strongpass123!',
                'password2': 'DifferentPass123!',
            },
            follow=True,
        )

        self.assertContains(response, 'do not match', status_code=200)


class PasswordResetFlowTest(TestCase):
    def test_password_reset_confirm_redirects_to_login(self):
        user = get_user_model().objects.create_user(
            username='resetuser',
            email='reset@example.com',
            password='OldPassword123!'
        )
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        token_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        redirect_response = self.client.get(token_url)

        self.assertEqual(redirect_response.status_code, 302)
        set_password_url = redirect_response.url

        response = self.client.post(
            set_password_url,
            {'new_password1': 'NewPassword123!', 'new_password2': 'NewPassword123!'},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))
