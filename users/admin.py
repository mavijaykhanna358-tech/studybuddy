from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from django.contrib.auth.models import User


# A custom admin is required because TaskAdmin and SubjectAdmin use
# autocomplete on the user field, which needs search_fields and
# list_display to be declared on the user admin.

admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(UserAdmin):

    list_display = [
        'username',
        'email',
        'is_staff',
        'date_joined',
    ]

    search_fields = [
        'username',
        'email',
        'first_name',
        'last_name',
    ]

    list_select_related = [
        'date_joined',
    ]

    ordering = [
        '-date_joined',
    ]
