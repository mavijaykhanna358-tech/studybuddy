import importlib
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class EmailSettingsTest(SimpleTestCase):
    def test_default_email_backend_uses_resend(self):
        import project.settings as settings_module

        self.assertEqual(
            settings_module.EMAIL_BACKEND,
            'users.email_backend.ResendEmailBackend',
        )


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
