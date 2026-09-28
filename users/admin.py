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

    # list_select_related is deliberately not set. It once read
    # ['date_joined'], which is a plain column on auth.User and not a
    # relation, so the changelist passed it to select_related() and
    # died with
    #
    #   FieldError: Non-relational field given in select_related:
    #   'date_joined'. Choices are: (none)
    #
    # when it compiled the SQL. The error is deferred to query
    # compilation rather than raised when the option is read, which
    # is why the admin index still rendered and only the Users
    # changelist returned a 500.
    #
    # Nothing here is wrong now, because auth.User has no forward
    # ForeignKey or OneToOne at all: its only relations are the
    # groups and user_permissions many-to-many tables, which
    # select_related cannot join and which Django's own UserAdmin
    # leaves alone. Django's default of False is the correct value.
    # Do not add a field to this list without checking it is a
    # relation.

    ordering = [
        '-date_joined',
    ]
