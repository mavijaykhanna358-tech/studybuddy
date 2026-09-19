import importlib
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class EmailSettingsTest(SimpleTestCase):
    def test_default_email_backend_uses_smtp(self):
        import project.settings as settings_module

        self.assertEqual(
            settings_module.EMAIL_BACKEND,
            'django.core.mail.backends.smtp.EmailBackend',
        )


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
