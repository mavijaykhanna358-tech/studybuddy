from django.contrib.auth import authenticate, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.urls import reverse_lazy


class CustomPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    success_url = reverse_lazy('login')


def register(request):
    error = None

    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        email = (request.POST.get('email') or '').strip()
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if not username:
            error = 'Username is required.'
        elif User.objects.filter(username=username).exists():
            error = 'This username is already taken.'
        elif not password1 or not password2:
            error = 'Please enter and confirm your password.'
        elif password1 != password2:
            error = 'Passwords do not match.'
        elif len(password1) < 8:
            error = 'Password must be at least 8 characters long.'
        else:
            User.objects.create_user(username=username, email=email, password=password1)
            return redirect('login')

    return render(request, 'users/register.html', {'error': error})


@login_required
def profile(request):
    return render(request, 'users/profile.html', {'user': request.user})
