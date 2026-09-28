"""
Tests for `manage.py provision_admin`.

The command reaches the production database during a Render build,
so what matters most is not that it creates an administrator but
that it is inert without configuration, that it never touches a
second account, and that it never sets a password it was not asked
to set. Those are the properties asserted here, along with a real
sign-in through the admin site at the end.
"""

import os
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


# A password that satisfies the project's validators, and is
# distinctive enough that finding it in a log would be
# unmistakable.

STRONG_PASSWORD = 'Str0ng-Admin-Passphrase-90210'

# Rejected by CommonPasswordValidator, so the command must refuse it
# and must not echo it while doing so.

WEAK_PASSWORD = 'password123'

# Flags a bystander account must keep, whatever the command does.

BYPASSER_FLAGS = (
    'is_staff',
    'is_superuser',
    'is_active',
)


def make_user(username, **extra):

    return get_user_model().objects.create_user(
        username=username,
        email=extra.pop('email', f'{username}@example.com'),
        password=extra.pop('password', 'Bystander-Passphrase-4417'),
        **extra,
    )


def run(*args, django_env='production', **environment):

    """
    Run the command with the given environment.

    `DJANGO_ENV` is set per call so the tests read like a Render
    build. Returns the combined output; `CommandError` is allowed to
    propagate so a test can assert on it.
    """

    out = StringIO()
    err = StringIO()

    with mock.patch.dict(
        os.environ,
        environment,
        clear=False,
    ):

        # Ensure the variables the caller did not supply cannot
        # leak in from the surrounding environment.

        for name in (
            'ADMIN_USERNAME',
            'ADMIN_EMAIL',
            'ADMIN_PASSWORD',
        ):

            if name not in environment:

                os.environ.pop(name, None)

        with override_settings(DJANGO_ENV=django_env):

            call_command(
                'provision_admin',
                *args,
                stdout=out,
                stderr=err,
            )

    return out.getvalue() + err.getvalue()


@override_settings(DJANGO_ENV='production')
class InertByDefaultTests(TestCase):
    """The command must be harmless once the variables are gone."""

    def test_nothing_happens_without_a_username(self):

        output = run()

        self.assertEqual(
            get_user_model().objects.count(),
            0,
        )

        self.assertIn(
            'ADMIN_USERNAME is not set',
            output,
        )

    def test_a_password_on_its_own_does_nothing(self):

        output = run(ADMIN_PASSWORD=STRONG_PASSWORD)

        self.assertEqual(
            get_user_model().objects.count(),
            0,
        )

        self.assertIn(
            'ADMIN_USERNAME is not set',
            output,
        )

    def test_an_email_on_its_own_does_nothing(self):

        run(ADMIN_EMAIL='someone@example.com')

        self.assertEqual(
            get_user_model().objects.count(),
            0,
        )

    def test_the_command_succeeds_when_inert(self):
        """A failing build would block the deploy it is meant to help."""

        # run() would raise CommandError if the command failed, so
        # reaching the assertion is the check.

        self.assertIsInstance(
            run(),
            str,
        )


class CreateTests(TestCase):
    """Creating the account on the deploy that provisions it."""

    def test_it_creates_an_active_superuser(self):

        run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        user = get_user_model().objects.get(
            username='siteadmin'
        )

        self.assertEqual(user.email, 'admin@studybuddy.example')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_the_password_is_hashed_not_stored(self):

        run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        user = get_user_model().objects.get(
            username='siteadmin'
        )

        self.assertNotEqual(
            user.password,
            STRONG_PASSWORD,
        )

        self.assertTrue(
            user.check_password(STRONG_PASSWORD)
        )

    def test_the_password_is_never_written_to_the_output(self):

        output = run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.assertNotIn(STRONG_PASSWORD, output)

    def test_a_rejected_password_is_never_echoed(self):

        with self.assertRaises(CommandError) as caught:

            run(
                ADMIN_USERNAME='siteadmin',
                ADMIN_EMAIL='admin@studybuddy.example',
                ADMIN_PASSWORD=WEAK_PASSWORD,
            )

        self.assertNotIn(
            WEAK_PASSWORD,
            str(caught.exception),
        )

    def test_a_weak_password_is_refused_and_creates_nothing(self):

        with self.assertRaises(CommandError):

            run(
                ADMIN_USERNAME='siteadmin',
                ADMIN_EMAIL='admin@studybuddy.example',
                ADMIN_PASSWORD=WEAK_PASSWORD,
            )

        self.assertEqual(
            get_user_model().objects.count(),
            0,
        )

    def test_a_missing_password_is_refused_and_creates_nothing(self):

        with self.assertRaises(CommandError) as caught:

            run(
                ADMIN_USERNAME='siteadmin',
                ADMIN_EMAIL='admin@studybuddy.example',
            )

        self.assertIn(
            'ADMIN_PASSWORD is not set',
            str(caught.exception),
        )

        self.assertEqual(
            get_user_model().objects.count(),
            0,
        )

    def test_a_missing_email_is_refused_and_creates_nothing(self):

        with self.assertRaises(CommandError) as caught:

            run(
                ADMIN_USERNAME='siteadmin',
                ADMIN_PASSWORD=STRONG_PASSWORD,
            )

        self.assertIn(
            'ADMIN_EMAIL is not',
            str(caught.exception),
        )

        self.assertEqual(
            get_user_model().objects.count(),
            0,
        )

    def test_an_address_owned_by_another_staff_account_is_refused(self):

        make_user(
            'existingadmin',
            email='admin@studybuddy.example',
            is_staff=True,
        )

        with self.assertRaises(CommandError) as caught:

            run(
                ADMIN_USERNAME='siteadmin',
                ADMIN_EMAIL='admin@studybuddy.example',
                ADMIN_PASSWORD=STRONG_PASSWORD,
            )

        self.assertIn('already belongs', str(caught.exception))

        self.assertFalse(
            get_user_model().objects.filter(
                username='siteadmin'
            ).exists()
        )

    def test_it_reuses_an_address_held_by_a_non_staff_account(self):

        """Only a second administrator is a real duplicate."""

        make_user(
            'student',
            email='admin@studybuddy.example',
        )

        run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.assertTrue(
            get_user_model().objects.get(
                username='siteadmin'
            ).is_superuser
        )


class PromoteTests(TestCase):
    """Promoting an account that already exists."""

    def setUp(self):

        self.user = make_user('siteadmin')

    def test_it_promotes_an_ordinary_account(self):

        run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
        )

        self.user.refresh_from_db()

        self.assertTrue(self.user.is_staff)
        self.assertTrue(self.user.is_superuser)
        self.assertTrue(self.user.is_active)

    def test_promoting_needs_no_password_at_all(self):

        """This is what makes ADMIN_PASSWORD removable afterwards."""

        output = run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
        )

        self.assertNotIn(
            'ADMIN_PASSWORD',
            output,
        )

        self.user.refresh_from_db()

        self.assertTrue(self.user.is_superuser)

    def test_it_activates_a_deactivated_account(self):

        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

        run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
        )

        self.user.refresh_from_db()

        self.assertTrue(self.user.is_active)

    def test_it_fills_in_a_blank_email(self):

        self.user.email = ''
        self.user.save(update_fields=['email'])

        run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
        )

        self.user.refresh_from_db()

        self.assertEqual(
            self.user.email,
            'admin@studybuddy.example',
        )

    def test_it_never_overwrites_an_existing_email(self):

        self.user.email = 'original@studybuddy.example'
        self.user.save(update_fields=['email'])

        output = run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='new@studybuddy.example',
        )

        self.user.refresh_from_db()

        self.assertEqual(
            self.user.email,
            'original@studybuddy.example',
        )

        self.assertIn(
            'rather than overwriting it',
            output,
        )

    def test_a_stale_password_variable_does_not_reset_the_password(self):
        """The failure this guards against is a locked-out admin.

        Leaving ADMIN_PASSWORD on the service would otherwise set
        the same password on every deploy, quietly undoing any
        change made in the admin site.
        """

        original_hash = self.user.password

        run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.user.refresh_from_db()

        self.assertEqual(self.user.password, original_hash)

        self.assertTrue(
            self.user.check_password(
                'Bystander-Passphrase-4417'
            )
        )

        self.assertFalse(
            self.user.check_password(STRONG_PASSWORD)
        )

    def test_a_stale_password_is_never_echoed(self):

        output = run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.assertNotIn(STRONG_PASSWORD, output)

    def test_reset_password_changes_it_when_asked(self):

        run(
            '--reset-password',
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.user.refresh_from_db()

        self.assertTrue(
            self.user.check_password(STRONG_PASSWORD)
        )

    def test_reset_password_still_never_echoes_it(self):

        output = run(
            '--reset-password',
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.assertNotIn(STRONG_PASSWORD, output)

    def test_reset_password_without_the_variable_is_refused(self):

        with self.assertRaises(CommandError):

            run(
                '--reset-password',
                ADMIN_USERNAME='siteadmin',
                ADMIN_EMAIL='admin@studybuddy.example',
            )

        self.user.refresh_from_db()

        self.assertTrue(
            self.user.check_password(
                'Bystander-Passphrase-4417'
            )
        )

    def test_reset_password_still_refuses_a_weak_one(self):

        original_hash = self.user.password

        with self.assertRaises(CommandError):

            run(
                '--reset-password',
                ADMIN_USERNAME='siteadmin',
                ADMIN_EMAIL='admin@studybuddy.example',
                ADMIN_PASSWORD=WEAK_PASSWORD,
            )

        self.user.refresh_from_db()

        self.assertEqual(self.user.password, original_hash)

    def test_the_password_of_an_unrelated_account_is_untouched(self):

        run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
        )

        self.user.refresh_from_db()

        self.assertTrue(self.user.is_superuser)
        self.assertTrue(
            self.user.check_password(
                'Bystander-Passphrase-4417'
            )
        )


class OtherAccountsTests(TestCase):
    """No query in the command may reach a second row."""

    def setUp(self):

        self.bystanders = [
            make_user('student'),
            make_user('teacher', is_staff=True),
            make_user('deactivated', is_active=False),
        ]

        self.before = self.snapshot()

    def snapshot(self):

        return {
            user.username: (
                user.email,
                user.password,
                *(
                    getattr(user, flag)
                    for flag in BYPASSER_FLAGS
                ),
            )
            for user in self.bystanders
        }

    def test_promoting_one_account_leaves_the_others_alone(self):

        run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.assertEqual(
            self.snapshot(),
            self.before,
        )

    def test_reset_password_leaves_the_others_alone(self):

        make_user('siteadmin')

        run(
            '--reset-password',
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.assertEqual(
            self.snapshot(),
            self.before,
        )

    def test_a_refused_run_leaves_the_others_alone(self):

        with self.assertRaises(CommandError):

            run(
                ADMIN_USERNAME='siteadmin',
                ADMIN_EMAIL='admin@studybuddy.example',
                ADMIN_PASSWORD=WEAK_PASSWORD,
            )

        self.assertEqual(
            self.snapshot(),
            self.before,
        )


class RepeatRunTests(TestCase):
    """The build runs this on every deploy, so it must be repeatable."""

    def run_twice(self, **extra):

        for _ in range(2):

            run(
                ADMIN_USERNAME='siteadmin',
                ADMIN_EMAIL='admin@studybuddy.example',
                **extra,
            )

    def test_running_twice_creates_one_account(self):

        self.run_twice(ADMIN_PASSWORD=STRONG_PASSWORD)

        self.assertEqual(
            get_user_model().objects.filter(
                username='siteadmin'
            ).count(),
            1,
        )

    def test_running_twice_keeps_the_first_password(self):

        self.run_twice(ADMIN_PASSWORD=STRONG_PASSWORD)

        self.assertTrue(
            get_user_model()
            .objects.get(username='siteadmin')
            .check_password(STRONG_PASSWORD)
        )

    def test_a_second_run_reports_nothing_to_do(self):

        self.run_twice(ADMIN_PASSWORD=STRONG_PASSWORD)

        output = run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.assertIn(
            'is already an active superuser',
            output,
        )

    def test_a_promoted_account_survives_a_third_run(self):
        """A deploy after the variables are removed must not undo it."""

        make_user('siteadmin')

        self.run_twice()

        self.assertTrue(
            get_user_model()
            .objects.get(username='siteadmin')
            .is_superuser
        )


class DryRunTests(TestCase):
    """Preview without writing."""

    def test_it_reports_a_creation_without_creating(self):

        output = run(
            '--dry-run',
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.assertIn('would be created', output)

        self.assertEqual(
            get_user_model().objects.count(),
            0,
        )

    def test_it_reports_a_promotion_without_promoting(self):

        make_user('siteadmin')

        output = run(
            '--dry-run',
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
        )

        self.assertIn('would be updated', output)

        user = get_user_model().objects.get(
            username='siteadmin'
        )

        self.assertFalse(user.is_superuser)

    def test_it_warns_that_a_missing_password_would_fail(self):

        output = run(
            '--dry-run',
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
        )

        self.assertIn(
            'would fail here',
            output,
        )

    def test_it_reports_a_conflicting_address(self):

        make_user(
            'existingadmin',
            email='admin@studybuddy.example',
            is_staff=True,
        )

        output = run(
            '--dry-run',
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.assertIn('would refuse', output)


class NonProductionTests(TestCase):
    def test_it_says_when_it_is_not_production(self):

        output = run(
            django_env='development',
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.assertIn(
            'is not the production database',
            output,
        )

    def test_the_warning_does_not_prevent_the_creation(self):

        run(
            django_env='development',
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        self.assertTrue(
            get_user_model()
            .objects.get(username='siteadmin')
            .is_superuser
        )


class RealSignInTests(TestCase):
    """The whole point: the account can reach the admin site."""

    def test_the_provisioned_account_can_use_the_admin_site(self):

        run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
            ADMIN_PASSWORD=STRONG_PASSWORD,
        )

        signed_in = self.client.login(
            username='siteadmin',
            password=STRONG_PASSWORD,
        )

        self.assertTrue(signed_in)

        response = self.client.get('/admin/')

        self.assertEqual(response.status_code, 200)

    def test_a_promoted_ordinary_account_can_use_the_admin_site(self):

        make_user(
            'siteadmin',
            password=STRONG_PASSWORD,
        )

        run(
            ADMIN_USERNAME='siteadmin',
            ADMIN_EMAIL='admin@studybuddy.example',
        )

        self.assertTrue(
            self.client.login(
                username='siteadmin',
                password=STRONG_PASSWORD,
            )
        )

        self.assertEqual(
            self.client.get('/admin/').status_code,
            200,
        )

    def test_the_admin_site_stays_closed_to_ordinary_accounts(self):
        """The command must not have widened anything else."""

        make_user('student', password=STRONG_PASSWORD)

        self.assertTrue(
            self.client.login(
                username='student',
                password=STRONG_PASSWORD,
            )
        )

        response = self.client.get('/admin/')

        self.assertEqual(response.status_code, 302)
