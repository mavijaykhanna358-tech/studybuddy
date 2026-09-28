import logging
from urllib.parse import urlparse

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    PasswordResetForm as BasePasswordResetForm,
)
from django.contrib.auth.forms import (
    SetPasswordForm as BaseSetPasswordForm,
)
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


logger = logging.getLogger(__name__)


User = get_user_model()


# ============================================================
# REGISTRATION FORM
# ============================================================

class RegistrationForm(forms.Form):

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                'class': 'sb-input',
                'placeholder': 'Choose a username',
                'autocomplete': 'username',
                'autofocus': True,
            }
        ),
    )

    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                'class': 'sb-input',
                'placeholder': 'you@example.com',
                'autocomplete': 'email',
            }
        ),
    )

    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(
            attrs={
                'class': 'sb-input',
                'placeholder': 'At least 8 characters',
                'autocomplete': 'new-password',
            }
        ),
    )

    password2 = forms.CharField(
        label='Confirm password',
        widget=forms.PasswordInput(
            attrs={
                'class': 'sb-input',
                'placeholder': 'Repeat your password',
                'autocomplete': 'new-password',
            }
        ),
    )

    def clean_username(self):

        username = self.cleaned_data['username'].strip()

        if not username:

            raise forms.ValidationError(
                'Username is required.'
            )

        if (
            User.objects
            .filter(username__iexact=username)
            .exists()
        ):

            raise forms.ValidationError(
                'This username is already taken.'
            )

        return username

    def clean_email(self):

        email = self.cleaned_data['email'].strip().lower()

        if (
            User.objects
            .filter(email__iexact=email)
            .exists()
        ):

            raise forms.ValidationError(
                'An account with this email already exists.'
            )

        return email

    def clean_password2(self):

        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')

        if password1 != password2:

            raise forms.ValidationError(
                'Passwords do not match.'
            )

        return password2

    def clean_password1(self):

        password = self.cleaned_data.get('password1')

        try:

            # Runs the same validators configured in
            # AUTH_PASSWORD_VALIDATORS, so registration cannot
            # create a password that a user could never set
            # through the admin or the API.

            validate_password(password)

        except ValidationError as error:

            raise forms.ValidationError(
                list(error.messages)
            ) from error

        return password

    def save(self):

        return User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password1'],
        )


# ============================================================
# PASSWORD RESET FORM
# ============================================================

class StyledPasswordResetForm(BasePasswordResetForm):
    """`PasswordResetForm` with the project input classes applied
    and without the silent failure on send.

    Django's version logs an exception and carries on, so a
    misconfigured mail provider leaves the user staring at a
    "check your inbox" page for a message that will never arrive.
    Here the error is re-raised, which surfaces the problem
    instead of hiding it.
    """

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields['email'].widget.attrs.update({
            'class': 'sb-input',
            'autocomplete': 'email',
            'placeholder': 'you@example.com',
        })

    def send_mail(self, *args, **kwargs):

        try:

            super().send_mail(*args, **kwargs)

        except Exception:

            logger.exception(
                'Failed to send the password reset email.'
            )

            raise

    def save(self, **kwargs):

        # Django builds the reset link from the host of the
        # incoming request, which produces a dead link whenever
        # the app is reached through a different hostname (a
        # preview domain, a custom domain, or `testserver`).
        # FRONTEND_BASE_URL is the single place the public address
        # is configured, so the link is built from it. An explicit
        # argument still wins.

        # The view always passes `use_https`, derived from the
        # scheme of the incoming request, so it is replaced rather
        # than defaulted. A request that arrives over plain HTTP
        # behind a TLS terminating proxy would otherwise produce
        # an `http://` link in the email.

        base_url = urlparse(
            settings.FRONTEND_BASE_URL
        )

        kwargs['domain_override'] = base_url.netloc
        kwargs['use_https'] = (
            base_url.scheme == 'https'
        )

        return super().save(**kwargs)


# ============================================================
# SET PASSWORD FORM
# ============================================================

class StyledSetPasswordForm(BaseSetPasswordForm):
    """`SetPasswordForm` with the project input classes applied.

    The classes are set on the widget here rather than with
    `as_widget(attrs=...)` in the template, because Django's
    template language cannot build a dict literal inside a filter
    argument. Doing it in Python also means the form is correct
    anywhere else it is rendered.
    """

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        for field in self.fields.values():

            widget = field.widget

            widget.attrs['class'] = 'sb-input'
            widget.attrs.setdefault(
                'autocomplete',
                'new-password'
            )
