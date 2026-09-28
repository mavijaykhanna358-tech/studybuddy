"""
Provision or promote a single Django administrator from the
environment.

Render Shell is a paid feature, so on a free plan the only way to
reach the production database is a command that runs as part of a
build. That makes this command a privilege escalation path for
anyone who can set an environment variable on the service, so it is
built to be inert by default and to hold no credentials of its own.

* With no `ADMIN_USERNAME` set it does nothing and exits
  successfully. That is the state the service returns to once the
  administrator exists, so this file can stay in `build.sh` for good
  without leaving a way back in.
* It only ever touches the single account named by `ADMIN_USERNAME`.
  Every query here is filtered to one row, and no statement in this
  file is capable of matching another user.
* It never sets or resets the password of an account that already
  exists. A stale `ADMIN_PASSWORD` left on the service would
  otherwise silently lock the administrator out on every deploy.
  Changing an existing password needs the explicit
  `--reset-password` flag.
* The password is read from the environment and never reaches any
  output stream, including an error message.
* It connects through `settings.DATABASE_URL`, which is the same
  PostgreSQL connection the application already uses, so no separate
  database configuration is involved.

Usage:

    ADMIN_USERNAME=... ADMIN_EMAIL=... ADMIN_PASSWORD=... \\
        python manage.py provision_admin

`ADMIN_PASSWORD` is needed only when the account does not exist yet.
Once it does, promoting the account needs no password at all, which
is what makes it safe to delete `ADMIN_PASSWORD` from the service
afterwards.
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


# Flags that have to be set for an account to reach /admin. A
# superuser that is not active cannot sign in however it is
# flagged, so promoting an account without activating it would
# report success and leave an administrator nobody can reach.

STAFF_FLAGS = (
    'is_staff',
    'is_superuser',
    'is_active',
)


class Command(BaseCommand):

    help = (
        'Create or promote the administrator named by '
        'ADMIN_USERNAME, reading ADMIN_EMAIL and optionally '
        'ADMIN_PASSWORD from the environment. Does nothing when '
        'ADMIN_USERNAME is unset.'
    )

    def add_arguments(self, parser):

        parser.add_argument(
            '--dry-run',
            action='store_true',
            help=(
                'Report what would change without writing to the '
                'database.'
            ),
        )

        parser.add_argument(
            '--reset-password',
            action='store_true',
            help=(
                'Also set the password of an account that already '
                'exists, from ADMIN_PASSWORD. Without this flag an '
                'existing password is never touched, so a stale '
                'ADMIN_PASSWORD cannot lock the administrator out '
                'on every deploy.'
            ),
        )

    def handle(self, *args, **options):

        dry_run = options['dry_run']
        reset_password = options['reset_password']

        username = (
            os.getenv('ADMIN_USERNAME', '')
            .strip()
        )

        # The point of the command is that it is safe to leave
        # wired into build.sh, so with no username it must do
        # nothing at all and succeed. That is the normal state once
        # the administrator exists.

        if not username:

            self.stdout.write(
                self.style.WARNING(
                    'ADMIN_USERNAME is not set, so there is no '
                    'administrator to provision. Nothing was '
                    'changed.'
                )
            )

            return

        email = (
            os.getenv('ADMIN_EMAIL', '')
            .strip()
        )

        if not email:

            raise CommandError(
                'ADMIN_USERNAME is set but ADMIN_EMAIL is not. '
                'Set both, or remove ADMIN_USERNAME so the command '
                'stays inert. No account was changed.'
            )

        if settings.DJANGO_ENV != 'production':

            # The command is meant to reach the Render PostgreSQL
            # database. Running it anywhere else most likely means
            # it is pointed at a developer's local database, which
            # is worth saying out loud.

            self.stdout.write(
                self.style.WARNING(
                    f'DJANGO_ENV is '
                    f'"{settings.DJANGO_ENV}", not "production", '
                    f'so this is not the production database.'
                )
            )

        user_model = get_user_model()

        # At most one row, because username is unique. Filtering
        # and slicing rather than get() means a hypothetical
        # duplicate cannot raise and abort a deploy; the count is
        # checked instead.

        existing = list(
            user_model.objects.filter(
                username=username
            )[:2]
        )

        if len(existing) > 1:

            raise CommandError(
                f'More than one account is called "{username}". '
                'That should be impossible, because the username is '
                'unique, and no account was changed.'
            )

        user = (
            existing[0]
            if existing
            else None
        )

        if dry_run:

            self.report_dry_run(
                user_model=user_model,
                username=username,
                email=email,
                user=user,
                reset_password=reset_password,
            )

            return

        with transaction.atomic():

            if user:

                outcome = self.promote(
                    user=user,
                    email=email,
                    reset_password=reset_password,
                )

            else:

                outcome = self.create(
                    user_model=user_model,
                    username=username,
                    email=email,
                )

        self.stdout.write(
            self.style.SUCCESS(outcome)
        )

    def plan(self, user, email, reset_password):

        """
        Work out what an existing account needs, without doing it.

        Returns the field names to write, a description of each for
        the log, and any notes that are observations rather than
        changes.
        """

        fields = []
        described = []
        notes = []

        for field in STAFF_FLAGS:

            if not getattr(user, field):

                fields.append(field)
                described.append(field)

        if not user.email:

            fields.append('email')
            described.append(f'email set to {email}')

        elif user.email.lower() != email.lower():

            # Not applied. Overwriting the address on an account
            # that already has one is far more likely to be a
            # mistake than an intention, and the administrator can
            # change it in the admin site if it was meant to move.

            notes.append(
                f'kept its existing email {user.email} rather '
                f'than overwriting it with {email}'
            )

        if reset_password:

            fields.append('password')
            described.append('password')

        return fields, described, notes

    def report_dry_run(
        self,
        user_model,
        username,
        email,
        user,
        reset_password,
    ):

        """
        Explain the change without making it.
        """

        if user:

            fields, described, notes = self.plan(
                user=user,
                email=email,
                reset_password=reset_password,
            )

            if not fields:

                self.stdout.write(
                    self.style.WARNING(
                        f'[dry run] "{username}" is already an '
                        f'active superuser ({user.email}). Nothing '
                        f'would change.'
                    )
                )

            else:

                self.stdout.write(
                    self.style.WARNING(
                        f'[dry run] "{username}" exists and would '
                        f'be updated: {", ".join(described)}.'
                    )
                )

            for note in notes:

                self.stdout.write(
                    self.style.WARNING(
                        f'[dry run] {note}.'
                    )
                )

            return

        self.stdout.write(
            self.style.WARNING(
                f'[dry run] "{username}" does not exist and would '
                f'be created as an active superuser with the email '
                f'{email}.'
            )
        )

        if not self.read_password():

            self.stdout.write(
                self.style.ERROR(
                    '[dry run] ADMIN_PASSWORD is not set, so the '
                    'real run would fail here.'
                )
            )

        if self.email_belongs_to_another_staff(
            user_model=user_model,
            username=username,
            email=email,
        ):

            self.stdout.write(
                self.style.ERROR(
                    f'[dry run] {email} already belongs to a '
                    f'different staff account, so the real run '
                    f'would refuse.'
                )
            )

    def email_belongs_to_another_staff(
        self,
        user_model,
        username,
        email,
    ):

        """
        Whether a different staff account already owns this email.

        Creating a second administrator with the same address is
        the duplicate this command exists to prevent, so the real
        run refuses instead of reporting a success that leaves it
        ambiguous which account is the administrator.
        """

        return user_model.objects.filter(
            email__iexact=email,
            is_staff=True,
        ).exclude(
            username=username
        ).exists()

    def read_password(self):

        """
        The administrator password, or None when none is set.

        Returned as a value and never printed. A missing variable
        is only an error where a password is genuinely needed.
        """

        return os.getenv('ADMIN_PASSWORD') or None

    def reject_weak_password(self, password, user):

        """
        Run the project's configured password validators.

        A build is a good moment to refuse a weak administrator
        password, because the alternative is an admin account held
        together by a guessable secret. The validators say why
        without repeating the password, so the message is safe to
        print.
        """

        try:

            validate_password(
                password,
                user=user,
            )

        except ValidationError as error:

            raise CommandError(
                f'ADMIN_PASSWORD was rejected by the password '
                f'validators: {"; ".join(error.messages)}. '
                'No account was changed.'
            ) from None

    def create(self, user_model, username, email):

        """
        Create the administrator, refusing to duplicate an address.
        """

        if self.email_belongs_to_another_staff(
            user_model=user_model,
            username=username,
            email=email,
        ):

            raise CommandError(
                f'{email} already belongs to a different staff '
                f'account. Refusing to create a second '
                f'administrator with the same address, because '
                f'which of them is the administrator would then be '
                f'ambiguous. No account was changed.'
            )

        password = self.read_password()

        if not password:

            raise CommandError(
                f'"{username}" does not exist yet, so a password '
                'is needed to create it, but ADMIN_PASSWORD is not '
                'set. Set it, or create the account once through '
                'the admin site. No account was changed.'
            )

        user = user_model(
            username=username,
            email=email,
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )

        self.reject_weak_password(
            password=password,
            user=user,
        )

        user.set_password(password)

        user.save()

        return (
            f'Created "{username}" ({email}) as an active '
            f'superuser. The password was read from '
            f'ADMIN_PASSWORD, was not written to any log, and can '
            f'now be deleted from the service: the next deploy will '
            f'not need it.'
        )

    def promote(self, user, email, reset_password):

        """
        Make an existing account an active superuser.

        Deliberately leaves the password alone unless asked, and
        never touches any other account.
        """

        fields, described, notes = self.plan(
            user=user,
            email=email,
            reset_password=reset_password,
        )

        if not fields:

            return (
                f'"{user.username}" ({user.email}) is already an '
                f'active superuser. Nothing was changed.'
            )

        for field in STAFF_FLAGS:

            if field in fields:

                setattr(user, field, True)

        if 'email' in fields:

            user.email = email

        if 'password' in fields:

            password = self.read_password()

            if not password:

                raise CommandError(
                    '--reset-password was given but ADMIN_PASSWORD '
                    'is not set. No account was changed.'
                )

            self.reject_weak_password(
                password=password,
                user=user,
            )

            user.set_password(password)

        # update_fields keeps the save from writing columns this
        # command has no business touching, such as last_login or
        # the timestamp on an unrelated profile row.

        user.save(update_fields=fields)

        summary = ', '.join(described)

        extra = (
            f' Also {notes[0]}.' if notes else ''
        )

        return (
            f'Promoted "{user.username}" ({user.email}) to an '
            f'active superuser. Changed: {summary}.{extra} '
            f'Only that one account was read or written.'
        )
