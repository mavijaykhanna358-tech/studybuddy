from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from .forms import (
    PasswordResetEmailError,
    RegistrationForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)


class CustomPasswordResetView(
    auth_views.PasswordResetView
):

    # The domain and scheme of the emailed link are handled by
    # StyledPasswordResetForm, which defaults them to
    # FRONTEND_BASE_URL.

    form_class = StyledPasswordResetForm

    # Shown when the provider rejected the send. Django would
    # otherwise redirect to "check your inbox" for a message that
    # does not exist, which is the failure this whole flow exists to
    # avoid.

    delivery_failed_message = (
        'We could not send the reset email just now. '
        'Please try again in a few minutes, or contact support '
        'if it keeps happening.'
    )

    def form_valid(self, form):

        try:

            return super().form_valid(form)

        except PasswordResetEmailError:

            form.add_error(
                None,
                self.delivery_failed_message
            )

            return self.form_invalid(form)


class CustomPasswordResetConfirmView(
    auth_views.PasswordResetConfirmView
):
    form_class = StyledSetPasswordForm
    success_url = reverse_lazy('login')


def register(request):

    if request.method == 'POST':

        form = RegistrationForm(
            request.POST
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                'Account created. '
                'You can now log in.'
            )

            return redirect('login')

    else:

        form = RegistrationForm()

    return render(
        request,
        'users/register.html',
        {
            'form': form
        }
    )


@login_required
def profile(request):

    return render(
        request,
        'users/profile.html',
        {
            'user': request.user
        }
    )
