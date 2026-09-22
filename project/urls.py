from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path


def root_redirect(request):

    if request.user.is_authenticated:
        return redirect('dashboard')

    return redirect('login')


urlpatterns = [

    # Home
    path(
        '',
        root_redirect,
        name='home'
    ),

    # Dashboard
    path(
        'dashboard/',
        include('dashboard.urls')
    ),

    # Users
    path(
        '',
        include('users.urls')
    ),

    # Subjects, Tasks, Notes
    path(
        '',
        include('tasks.urls')
    ),

    # Admin
    path(
        'admin/',
        admin.site.urls
    ),

]


# Media files
if settings.DEBUG:

    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )