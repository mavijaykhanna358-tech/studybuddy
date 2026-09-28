"""
Tests for `manage.py send_task_reminders`.

The command is run by a scheduled GitHub Action, so it is
exercised here with a real (locmem) mailbox instead of a live
provider.
"""

from datetime import date, timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.mail import send_mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from tasks.models import Subject, Task


TODAY = date.today()

TOMORROW = TODAY + timedelta(days=1)

YESTERDAY = TODAY - timedelta(days=1)


def make_user(username, email=None):

    return get_user_model().objects.create_user(
        username=username,
        email=(
            email
            if email is not None
            else f'{username}@example.com'
        ),
        password='Pass123!',
    )


def run_command(*args):
    out = StringIO()
    err = StringIO()

    call_command(
        'send_task_reminders',
        *args,
        stdout=out,
        stderr=err,
    )

    return out.getvalue(), err.getvalue()


class SendTaskRemindersTests(TestCase):
    def setUp(self):
        self.user = make_user('student')

    def test_no_tasks_sends_nothing(self):
        run_command()

        self.assertEqual(len(mail.outbox), 0)

    def test_task_due_tomorrow_is_reminded(self):
        Task.objects.create(
            user=self.user,
            title='Finish lab report',
            due_date=TOMORROW
        )

        run_command()

        self.assertEqual(len(mail.outbox), 1)

        message = mail.outbox[0]

        self.assertIn(
            'Finish lab report',
            message.subject
        )

        self.assertEqual(
            message.to,
            [self.user.email]
        )

    def test_overdue_task_is_reminded_with_overdue_wording(self):
        Task.objects.create(
            user=self.user,
            title='Hand in essay',
            due_date=YESTERDAY
        )

        run_command()

        self.assertEqual(len(mail.outbox), 1)

        message = mail.outbox[0]

        self.assertIn('Overdue', message.subject)
        self.assertIn('now overdue', message.body)

    def test_task_due_later_is_not_reminded(self):
        Task.objects.create(
            user=self.user,
            title='Next week',
            due_date=TODAY + timedelta(days=7)
        )

        run_command()

        self.assertEqual(len(mail.outbox), 0)

    def test_completed_task_is_not_reminded(self):
        Task.objects.create(
            user=self.user,
            title='Already done',
            status='Completed',
            due_date=TOMORROW
        )

        run_command()

        self.assertEqual(len(mail.outbox), 0)

    def test_task_without_a_due_date_is_not_reminded(self):
        Task.objects.create(
            user=self.user,
            title='Someday'
        )

        run_command()

        self.assertEqual(len(mail.outbox), 0)

    def test_user_without_an_email_is_not_reminded(self):
        user = make_user('noemail', email='')

        Task.objects.create(
            user=user,
            title='Nobody to tell',
            due_date=TOMORROW
        )

        run_command()

        self.assertEqual(len(mail.outbox), 0)

    def test_a_task_is_only_reminded_once(self):
        task = Task.objects.create(
            user=self.user,
            title='Send once',
            due_date=TOMORROW
        )

        run_command()

        task.refresh_from_db()

        self.assertIsNotNone(task.reminder_sent_at)

        run_command()

        self.assertEqual(len(mail.outbox), 1)

    def test_changing_the_due_date_allows_a_new_reminder(self):
        task = Task.objects.create(
            user=self.user,
            title='Rescheduled',
            due_date=TODAY + timedelta(days=5)
        )

        Task.objects.filter(pk=task.pk).update(
            reminder_sent_at=timezone.now()
        )

        task.refresh_from_db()
        task.due_date = TOMORROW
        task.save()

        run_command()

        self.assertEqual(len(mail.outbox), 1)

    def test_dry_run_sends_nothing_and_records_nothing(self):
        task = Task.objects.create(
            user=self.user,
            title='Preview only',
            due_date=TOMORROW
        )

        out, _ = run_command('--dry-run')

        task.refresh_from_db()

        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(task.reminder_sent_at)
        self.assertIn('dry run', out.lower())

    def test_subject_name_is_included_when_set(self):
        subject = Subject.objects.create(
            user=self.user,
            name='Physics'
        )

        Task.objects.create(
            user=self.user,
            subject=subject,
            title='Lab write up',
            due_date=TOMORROW
        )

        run_command()

        self.assertIn('Physics', mail.outbox[0].body)

    def test_one_bad_mailbox_does_not_stop_the_run(self):
        good_user = make_user('good')

        broken = Task.objects.create(
            user=self.user,
            title='Broken mailbox',
            due_date=YESTERDAY
        )

        good = Task.objects.create(
            user=good_user,
            title='Fine mailbox',
            due_date=TOMORROW
        )

        real_send_mail = send_mail

        def flaky_send_mail(**kwargs):

            # Fail only for the first recipient.

            if kwargs['recipient_list'] == [self.user.email]:

                raise OSError('Mailbox unavailable')

            return real_send_mail(**kwargs)

        with mock.patch(
            'tasks.management.commands.send_task_reminders.send_mail',
            side_effect=flaky_send_mail,
        ):

            _, err = run_command()

        broken.refresh_from_db()
        good.refresh_from_db()

        # The failing task is retried on the next run, while the
        # rest of the run carries on.

        self.assertIsNone(broken.reminder_sent_at)
        self.assertIsNotNone(good.reminder_sent_at)
        self.assertIn('Broken mailbox', err)

    def test_a_returned_zero_does_not_mark_the_task_as_reminded(self):
        task = Task.objects.create(
            user=self.user,
            title='Silently dropped',
            due_date=TOMORROW
        )

        with mock.patch(
            'tasks.management.commands.send_task_reminders.send_mail',
            return_value=0,
        ):

            _, err = run_command()

        task.refresh_from_db()

        self.assertIsNone(task.reminder_sent_at)
        self.assertIn('Silently dropped', err)
