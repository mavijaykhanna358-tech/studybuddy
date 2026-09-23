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

    path(
        '',
        root_redirect,
        name='home'
    ),

    path(
        'dashboard/',
        include('dashboard.urls')
    ),

    path(
        '',
        include('users.urls')
    ),

    path(
        '',
        include('tasks.urls')
    ),

    path(
        'admin/',
        admin.site.urls
    ),

]


# Serve uploaded files
urlpatterns += static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT
)