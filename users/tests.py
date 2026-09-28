import importlib.util
import io
import os
import re
from contextlib import redirect_stderr
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import checks, mail
from django.core.checks import Tags
from django.core.exceptions import ImproperlyConfigured
from django.test import (
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from project.deployment import (
    deployment_configuration,
    refuse_to_start,
)
from project.settings import BASE_DIR


SETTINGS_PATH = BASE_DIR / 'project' / 'settings.py'

STRONG_SECRET_KEY = 'unit-test-secret-key-that-is-long-enough-to-pass-checks-0123456789'

CONSOLE_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# A production settings load records a problem when there is no
# DATABASE_URL, because a deployment with no database would fall back
# to SQLite on an ephemeral disk. The tests below simulate a production
# environment to check DEBUG and email behaviour, so they need a
# syntactically valid URL and must not report anything. Nothing ever
# connects to it.
PRODUCTION_DATABASE_URL = (
    'postgresql://unit-test:unit-test@db.example.invalid:5432/studybuddy'
)

# Never a real credential. The Resend API key is only ever compared
# for presence, and a request is never actually made with it.
PRODUCTION_RESEND_API_KEY = 're_unit_test_not_a_real_key'

# A sending address on a domain that is not Resend's shared testing
# domain, which only delivers to the account owner.
PRODUCTION_SENDER = 'no-reply@studybuddy.example'


def production_environment(**overrides):
    """
    A complete, correct production environment for a settings load.

    Any production load that is not about a specific missing variable
    starts from here, so a test that is about the database or about
    DEBUG does not also collect an unrelated email complaint.
    """
    environment = {
        'DJANGO_ENV': 'production',
        'SECRET_KEY': STRONG_SECRET_KEY,
        'RESEND_API_KEY': PRODUCTION_RESEND_API_KEY,
        'DEFAULT_FROM_EMAIL': PRODUCTION_SENDER,
    }

    environment.update(overrides)

    return environment


def reset_path_from(body):
    """The site-relative reset URL from an emailed body.

    The link is absolute and points at the public site, so only the
    path is usable against the test client.
    """
    match = re.search(r'https?://[^\s/]+(/reset/\S+)', body)

    if match is None:

        raise AssertionError(
            f'no reset link in the email body: {body!r}'
        )

    return match.group(1)


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
            **production_environment(
                DATABASE_URL=PRODUCTION_DATABASE_URL,
                RESEND_API_KEY='re_test_key',
            )
        )

        self.assertEqual(
            settings.EMAIL_BACKEND,
            'users.email_backend.ResendEmailBackend',
        )

    def test_console_backend_is_used_in_development(self):
        """Locally, mail is printed to the terminal. That is fine."""
        settings = load_settings(
            DJANGO_ENV='development',
            RESEND_API_KEY=None,
        )

        self.assertEqual(
            settings.EMAIL_BACKEND,
            CONSOLE_BACKEND,
        )

    def test_production_never_falls_back_to_the_console(self):
        """The console backend is what made this fail silently.

        In production it printed the reset email into the gunicorn
        log, threw it away, and the user was still redirected to the
        "check your inbox" page. Production must therefore keep the
        Resend backend even with no key, so the send fails loudly and
        the deployment check names the missing variable.
        """
        settings = load_settings(
            **production_environment(
                DATABASE_URL=PRODUCTION_DATABASE_URL,
                RESEND_API_KEY=None,
            )
        )

        self.assertEqual(
            settings.EMAIL_BACKEND,
            'users.email_backend.ResendEmailBackend',
        )

    def test_a_missing_api_key_is_reported_in_production(self):
        settings = load_settings(
            **production_environment(
                DATABASE_URL=PRODUCTION_DATABASE_URL,
                RESEND_API_KEY=None,
            )
        )

        self.assertIn(
            'RESEND_API_KEY',
            [
                identifier
                for identifier, _ in settings.DEPLOYMENT_ERRORS
            ],
        )

    def test_a_missing_api_key_is_not_reported_in_development(self):
        """No key is the expected local setup, so nothing is recorded."""
        settings = load_settings(
            DJANGO_ENV='development',
            RESEND_API_KEY=None,
        )

        self.assertEqual(settings.DEPLOYMENT_ERRORS, [])

    def test_the_testing_sender_is_reported_in_production(self):
        """Resend's shared domain only delivers to the account owner.

        Sending a reset from it to a real user is rejected with a 403,
        so a deployment still pointing at it cannot work.
        """
        settings = load_settings(
            **production_environment(
                DATABASE_URL=PRODUCTION_DATABASE_URL,
                DEFAULT_FROM_EMAIL='onboarding@resend.dev',
            )
        )

        identifiers = [
            identifier
            for identifier, _ in settings.DEPLOYMENT_ERRORS
        ]

        self.assertIn('DEFAULT_FROM_EMAIL', identifiers)

    def test_a_verified_sender_is_not_reported(self):
        settings = load_settings(
            **production_environment(
                DATABASE_URL=PRODUCTION_DATABASE_URL,
            )
        )

        self.assertEqual(settings.DEPLOYMENT_ERRORS, [])

    def test_explicit_email_backend_wins(self):
        settings = load_settings(
            **production_environment(
                DATABASE_URL=PRODUCTION_DATABASE_URL,
                EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
            )
        )

        self.assertEqual(
            settings.EMAIL_BACKEND,
            'django.core.mail.backends.locmem.EmailBackend',
        )

    def test_a_backend_that_cannot_deliver_is_reported(self):
        """Naming a console backend is the same failure as none.

        On Render its output goes to a log nobody reads, so the reset
        email is discarded while the page reports success. The
        variable is honoured, but the deployment is reported.
        """
        settings = load_settings(
            **production_environment(
                DATABASE_URL=PRODUCTION_DATABASE_URL,
                EMAIL_BACKEND=CONSOLE_BACKEND,
            )
        )

        self.assertEqual(settings.EMAIL_BACKEND, CONSOLE_BACKEND)

        self.assertIn(
            'EMAIL_BACKEND',
            [
                identifier
                for identifier, _ in settings.DEPLOYMENT_ERRORS
            ],
        )

    def test_a_delivering_backend_is_not_reported(self):
        settings = load_settings(
            **production_environment(
                DATABASE_URL=PRODUCTION_DATABASE_URL,
                EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
            )
        )

        self.assertEqual(settings.DEPLOYMENT_ERRORS, [])


class DebugSettingsTest(SimpleTestCase):
    def test_debug_is_on_by_default_for_development(self):
        settings = load_settings(
            DJANGO_ENV='development',
            DEBUG=None,
        )

        self.assertTrue(settings.DEBUG)

    def test_debug_is_off_by_default_for_production(self):
        settings = load_settings(
            **production_environment(
                DEBUG=None,
                DATABASE_URL=PRODUCTION_DATABASE_URL,
            )
        )

        self.assertFalse(settings.DEBUG)

    def test_debug_can_be_forced_on_for_a_production_env(self):
        settings = load_settings(
            **production_environment(
                DEBUG='True',
                DATABASE_URL=PRODUCTION_DATABASE_URL,
            )
        )

        self.assertTrue(settings.DEBUG)

    def test_debug_can_be_forced_off_for_a_development_env(self):
        settings = load_settings(
            DJANGO_ENV='development',
            DEBUG='False',
            SECRET_KEY=STRONG_SECRET_KEY,
        )

        self.assertFalse(settings.DEBUG)


class DatabaseSettingsTest(SimpleTestCase):
    """The deployment must resolve to a real database, never to nothing."""

    def problems(self, settings):
        """Return the identifiers of the problems a load recorded."""
        return [
            identifier
            for identifier, _ in settings.DEPLOYMENT_ERRORS
        ]

    def details(self, settings, identifier):
        """Return the recorded explanation for one problem."""
        return ' '.join(
            detail
            for name, detail in settings.DEPLOYMENT_ERRORS
            if name == identifier
        )

    def test_production_url_resolves_to_postgresql(self):
        settings = load_settings(
            **production_environment(
                DATABASE_URL=PRODUCTION_DATABASE_URL,
            )
        )

        self.assertEqual(
            settings.DATABASES['default']['ENGINE'],
            'django.db.backends.postgresql',
        )

    def test_production_url_keeps_the_connection_reuse_settings(self):
        settings = load_settings(
            **production_environment(
                DATABASE_URL=PRODUCTION_DATABASE_URL,
            )
        )

        default = settings.DATABASES['default']

        self.assertEqual(default['CONN_MAX_AGE'], 600)
        self.assertTrue(default['CONN_HEALTH_CHECKS'])

    def test_production_without_a_url_is_reported(self):
        """A missing URL is reported, not raised.

        The settings must still import, otherwise Django cannot find
        `collectstatic` and the build fails with
        "Unknown command: 'collectstatic'".
        """
        settings = load_settings(
            **production_environment(
                DATABASE_URL=None,
                DATABASE_FALLBACK_ENGINE=None,
            )
        )

        self.assertEqual(
            self.problems(settings),
            ['DATABASE_URL'],
        )

    def test_production_without_a_url_never_uses_sqlite(self):
        """Render's disk is ephemeral, so SQLite must not be the answer.

        A real deployment with no database would look healthy and then
        lose every row on the next deploy, so the dummy backend stands
        in and the system check stops the command instead.
        """
        settings = load_settings(
            **production_environment(
                DATABASE_URL=None,
                DATABASE_FALLBACK_ENGINE=None,
            )
        )

        self.assertEqual(
            settings.DATABASES['default']['ENGINE'],
            'django.db.backends.dummy',
        )

    def test_production_with_a_malformed_url_is_reported(self):
        settings = load_settings(
            **production_environment(DATABASE_URL='not-a-url')
        )

        self.assertEqual(
            self.problems(settings),
            ['DATABASE_URL'],
        )

        self.assertIn(
            'could not be parsed',
            self.details(settings, 'DATABASE_URL'),
        )

    def test_production_with_a_malformed_url_never_uses_sqlite(self):
        settings = load_settings(
            **production_environment(DATABASE_URL='not-a-url')
        )

        self.assertEqual(
            settings.DATABASES['default']['ENGINE'],
            'django.db.backends.dummy',
        )

    def test_a_correct_production_load_records_nothing(self):
        settings = load_settings(
            **production_environment(
                DATABASE_URL=PRODUCTION_DATABASE_URL,
            )
        )

        self.assertEqual(settings.DEPLOYMENT_ERRORS, [])

    def test_development_falls_back_to_sqlite(self):
        settings = load_settings(
            DJANGO_ENV='development',
            SECRET_KEY=STRONG_SECRET_KEY,
            DATABASE_URL=None,
            DATABASE_FALLBACK_ENGINE=None,
        )

        self.assertEqual(
            settings.DATABASES['default']['ENGINE'],
            'django.db.backends.sqlite3',
        )

    def test_sqlite_can_be_forced_back_on_in_production(self):
        settings = load_settings(
            **production_environment(
                DATABASE_URL=None,
                DATABASE_FALLBACK_ENGINE='django.db.backends.sqlite3',
            )
        )

        self.assertEqual(
            settings.DATABASES['default']['ENGINE'],
            'django.db.backends.sqlite3',
        )

    def test_internal_render_url_does_not_force_sslmode(self):
        """Render's internal database does not terminate TLS.

        Forcing `sslmode=require` there would fail the connection, so
        the default must leave the URL alone.
        """
        settings = load_settings(
            **production_environment(
                DATABASE_URL='postgresql://user:pass@dpg-abc123/studybuddy',
                DATABASE_SSL_REQUIRE=None,
            )
        )

        options = settings.DATABASES['default'].get('OPTIONS') or {}

        self.assertIsNone(options.get('sslmode'))

    def test_sslmode_in_the_url_is_always_honoured(self):
        """Render's external string carries `?sslmode=require`."""
        settings = load_settings(
            **production_environment(
                DATABASE_URL=(
                    'postgresql://user:pass@db.example.com:5432/studybuddy'
                    '?sslmode=require'
                ),
                DATABASE_SSL_REQUIRE=None,
            )
        )

        options = settings.DATABASES['default'].get('OPTIONS') or {}

        self.assertEqual(options.get('sslmode'), 'require')


class ProductionSecretsTest(SimpleTestCase):
    def test_weak_secret_key_is_reported_when_debug_is_off(self):
        """A short key must not abort the import.

        Raising here is what made a Render build stop with
        "Unknown command: 'collectstatic'": Django swallows the error
        from the settings, `get_commands` then returns only the core
        command list, and the real reason never reached the log.
        """
        settings = load_settings(
            **production_environment(
                DEBUG=None,
                SECRET_KEY='insecure',
                DATABASE_URL=PRODUCTION_DATABASE_URL,
            )
        )

        self.assertIn(
            'SECRET_KEY',
            [
                identifier
                for identifier, _ in settings.DEPLOYMENT_ERRORS
            ],
        )

    def test_weak_secret_key_is_allowed_while_debug_is_on(self):
        settings = load_settings(
            DJANGO_ENV='development',
            DEBUG=None,
            SECRET_KEY='insecure',
        )

        self.assertTrue(settings.DEBUG)
        self.assertEqual(settings.DEPLOYMENT_ERRORS, [])


class DeploymentReportTest(SimpleTestCase):
    """A broken deployment must say what is wrong.

    The failure this guards against is precise: when the settings
    module refused to import, Django reported
    "Unknown command: 'collectstatic'" and the actual reason was
    nowhere in the build log.
    """

    def test_a_broken_production_load_still_imports(self):
        settings = load_settings(
            **production_environment(
                DEBUG=None,
                SECRET_KEY='insecure',
                DATABASE_URL=None,
                DATABASE_FALLBACK_ENGINE=None,
                RESEND_API_KEY=None,
            )
        )

        self.assertEqual(
            sorted(
                identifier
                for identifier, _ in settings.DEPLOYMENT_ERRORS
            ),
            ['DATABASE_URL', 'RESEND_API_KEY', 'SECRET_KEY'],
        )

    def test_the_check_is_registered(self):
        """Without registration no command would ever report the problem."""
        self.assertIn(
            deployment_configuration,
            checks.registry.registry.get_checks(),
        )

    def test_the_check_is_tagged_for_collectstatic(self):
        """`collectstatic` runs only checks carrying this tag.

        Its `requires_system_checks` is `[Tags.staticfiles]`, and a
        check without that tag is filtered out, so the error would
        never reach the build log.
        """
        self.assertIn(Tags.staticfiles, deployment_configuration.tags)

    def test_a_recorded_problem_becomes_a_check_error(self):
        with override_settings(
            DEPLOYMENT_ERRORS=[('DATABASE_URL', 'is not set')],
        ):
            reported = deployment_configuration(app_configs=None)

        self.assertEqual(len(reported), 1)

        self.assertEqual(reported[0].id, 'studybuddy.database_url')
        self.assertIn('DATABASE_URL is not set', reported[0].msg)

    def test_every_problem_is_reported_separately(self):
        with override_settings(
            DEPLOYMENT_ERRORS=[
                ('DATABASE_URL', 'is not set'),
                ('SECRET_KEY', 'is too short'),
            ],
        ):
            reported = deployment_configuration(app_configs=None)

        self.assertEqual(
            [error.id for error in reported],
            [
                'studybuddy.database_url',
                'studybuddy.secret_key',
            ],
        )

    def test_a_correct_configuration_reports_nothing(self):
        with override_settings(DEPLOYMENT_ERRORS=[]):
            self.assertEqual(
                deployment_configuration(app_configs=None),
                [],
            )

    def test_the_web_server_refuses_to_start(self):
        """Gunicorn runs no system checks, so wsgi must fail on its own."""
        captured = io.StringIO()

        with override_settings(
            DEPLOYMENT_ERRORS=[('DATABASE_URL', 'is not set')],
        ):
            with redirect_stderr(captured):
                with self.assertRaises(ImproperlyConfigured) as caught:
                    refuse_to_start()

        self.assertIn('DATABASE_URL', str(caught.exception))
        self.assertIn('DATABASE_URL is not set', captured.getvalue())

    def test_the_web_server_starts_when_configured(self):
        captured = io.StringIO()

        with override_settings(DEPLOYMENT_ERRORS=[]):
            with redirect_stderr(captured):
                refuse_to_start()

        self.assertEqual(captured.getvalue(), '')


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

    def test_the_new_password_actually_takes_effect(self):
        """The link must really replace the old password.

        Everything else in this flow is a page that renders, so the
        only honest proof is that the stored hash changed and the new
        password logs in while the old one no longer does.
        """
        user = get_user_model().objects.create_user(
            username='roundtrip',
            email='roundtrip@example.com',
            password='OldPassword123!'
        )

        with override_settings(
            EMAIL_BACKEND=(
                'django.core.mail.backends.locmem.EmailBackend'
            ),
        ):

            self.client.post(
                reverse('password_reset'),
                {'email': 'roundtrip@example.com'},
            )

        self.assertEqual(len(mail.outbox), 1)

        # Django moves the token out of the URL and into the session,
        # so the GET is followed and the form is posted to wherever it
        # landed.

        confirmation = self.client.get(
            reset_path_from(mail.outbox[0].body)
        )

        self.assertEqual(confirmation.status_code, 302)

        self.client.post(
            confirmation['Location'],
            {
                'new_password1': 'BrandNewPassword123!',
                'new_password2': 'BrandNewPassword123!',
            },
        )

        user.refresh_from_db()

        self.assertTrue(
            user.check_password('BrandNewPassword123!')
        )

        self.assertFalse(
            user.check_password('OldPassword123!')
        )

        self.assertTrue(
            self.client.login(
                username='roundtrip',
                password='BrandNewPassword123!',
            )
        )


class PasswordResetDeliveryTest(TestCase):
    """A reset email that was never sent must not look like success.

    Django 5.2 sends the message inside a `try/except` that only
    logs, so an invalid API key, an unverified sender or a Resend
    testing-domain restriction all produced a redirect to "check your
    inbox" for a message that did not exist. These tests pin the
    behaviour that replaced it.
    """

    def setUp(self):

        self.user = get_user_model().objects.create_user(
            username='delivery',
            email='delivery@example.com',
            password='OldPassword123!'
        )

    def submit(self):
        return self.client.post(
            reverse('password_reset'),
            {'email': 'delivery@example.com'},
        )

    def test_a_rejected_send_is_not_reported_as_success(self):
        # Regression test. Before the fix this returned a 302 to
        # /password-reset/done/ and no email, which is the exact
        # symptom that was reported.

        with override_settings(
            EMAIL_BACKEND=(
                'users.email_backend.ResendEmailBackend'
            ),
            RESEND_API_KEY='re_unit_test_not_a_real_key',
        ):

            with mock.patch(
                'resend.Emails.send'
            ) as send:

                send.side_effect = OSError('Connection refused')

                response = self.submit()

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(
            response.get('Location'),
            reverse('password_reset_done'),
        )

    def test_a_rejected_send_tells_the_user_on_the_form(self):
        with override_settings(
            EMAIL_BACKEND=(
                'users.email_backend.ResendEmailBackend'
            ),
            RESEND_API_KEY='re_unit_test_not_a_real_key',
        ):

            with mock.patch(
                'resend.Emails.send'
            ) as send:

                send.side_effect = OSError('Connection refused')

                response = self.submit()

        self.assertContains(
            response,
            'could not send the reset email',
        )

    def test_a_rejected_send_never_reaches_the_done_page(self):
        with override_settings(
            EMAIL_BACKEND=(
                'users.email_backend.ResendEmailBackend'
            ),
            RESEND_API_KEY='re_unit_test_not_a_real_key',
        ):

            with mock.patch(
                'resend.Emails.send'
            ) as send:

                send.side_effect = OSError('Connection refused')

                response = self.submit(
                )

        self.assertNotContains(
            response,
            'Check your email',
            status_code=200,
        )

    def test_a_successful_send_still_reaches_the_done_page(self):
        with override_settings(
            EMAIL_BACKEND=(
                'users.email_backend.ResendEmailBackend'
            ),
            RESEND_API_KEY='re_unit_test_not_a_real_key',
        ):

            with mock.patch(
                'resend.Emails.send'
            ) as send:

                send.return_value = {'id': 'msg_test'}

                response = self.submit()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            reverse('password_reset_done'),
        )

    def test_the_email_is_multipart_with_a_plain_text_part(self):
        # Without a .txt template the HTML was the text/plain body and
        # the mail rendered as raw markup.

        with override_settings(
            EMAIL_BACKEND=(
                'django.core.mail.backends.locmem.EmailBackend'
            ),
        ):

            self.submit()

        self.assertEqual(len(mail.outbox), 1)

        sent = mail.outbox[0]

        self.assertIn('text/html', sent.alternatives[0][1])
        self.assertNotIn('<p>', sent.body)
        self.assertNotIn('<a ', sent.body)
        self.assertIn('/reset/', sent.body)
        self.assertIn('/reset/', sent.alternatives[0][0])

    def test_the_confirmation_form_shows_field_errors(self):
        # The confirm template iterated `form.fields.items()`, which
        # yields (name, Field) pairs, so the inner loop tried to
        # iterate a Field and the page raised a TypeError the moment a
        # password failed validation.

        user = self.user
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        confirmation = self.client.get(
            reverse(
                'password_reset_confirm',
                kwargs={'uidb64': uid, 'token': token},
            )
        )

        self.assertEqual(confirmation.status_code, 302)

        rejected = self.client.post(
            confirmation['Location'],
            {
                'new_password1': 'Short1!',
                'new_password2': 'Different2!',
            },
        )

        self.assertEqual(rejected.status_code, 200)
        self.assertContains(rejected, 'password fields didn')

        # A password the validators reject must render the same way
        # rather than raising.

        too_weak = self.client.post(
            confirmation['Location'],
            {
                'new_password1': 'password',
                'new_password2': 'password',
            },
        )

        self.assertEqual(too_weak.status_code, 200)

