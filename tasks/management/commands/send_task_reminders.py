from datetime import timedelta

from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from tasks.models import Task


class Command(BaseCommand):

    help = (
        'Send email reminders for tasks due tomorrow '
        'and for tasks that are now overdue.'
    )

    def add_arguments(self, parser):

        parser.add_argument(
            '--dry-run',
            action='store_true',
            help=(
                'Show what would be sent without sending '
                'any email or updating the database.'
            ),
        )

    def handle(self, *args, **options):

        dry_run = options['dry_run']

        today = timezone.localdate()

        tomorrow = today + timedelta(days=1)

        # Overdue tasks are included alongside tomorrow's tasks
        # because a missed deadline is more urgent than an
        # upcoming one. The two groups are told apart below so
        # the wording stays accurate.

        tasks = Task.objects.filter(
            Q(due_date__lte=tomorrow)
            & Q(reminder_sent_at__isnull=True)
        ).exclude(
            status='Completed'
        ).exclude(
            user__email=''
        ).select_related(
            'user',
            'subject'
        ).order_by(
            'due_date'
        )

        sent_count = 0

        skipped_count = 0

        for task in tasks.iterator():

            user = task.user

            if not user.email:

                skipped_count += 1

                self.stdout.write(
                    self.style.WARNING(
                        f'Skipped "{task.title}" - '
                        f'user has no email address.'
                    )
                )

                continue

            subject_name = (
                task.subject.name
                if task.subject
                else ''
            )

            if task.due_date < today:

                email_subject = (
                    f'Overdue task reminder: {task.title}'
                )

                opening = (
                    'This task was due '
                    f'{self.format_date(task.due_date)} '
                    'and is now overdue.'
                )

                closing = (
                    'Please finish it as soon as possible, or '
                    'update its due date if it needs more time.'
                )

            else:

                email_subject = (
                    f'Task Reminder: {task.title} '
                    'is due tomorrow'
                )

                opening = (
                    'This is a reminder that your task is '
                    'due tomorrow.'
                )

                closing = (
                    'Tomorrow is the last day to finish this '
                    'task. Please complete it before the due '
                    'date.'
                )

            email_message = (
                f'Hello {user.username},\n\n'
                f'{opening}\n\n'
                f'Task: {task.title}\n'
            )

            if subject_name:

                email_message += f'Subject: {subject_name}\n'

            email_message += (
                f'Due date: {self.format_date(task.due_date)}\n'
                f'\n{closing}\n'
                f'\nRegards,\nStudyBuddy\n'
            )

            if dry_run:

                self.stdout.write(
                    self.style.WARNING(
                        f'[dry run] Would email {user.email} - '
                        f'"{task.title}"'
                    )
                )

                continue

            try:

                sent = send_mail(
                    subject=email_subject,
                    message=email_message,
                    from_email=None,
                    recipient_list=[user.email],
                    fail_silently=False,
                )

                if sent:

                    task.reminder_sent_at = timezone.now()

                    task.save(
                        update_fields=[
                            'reminder_sent_at'
                        ]
                    )

                    sent_count += 1

                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Reminder sent for '
                            f'"{task.title}" '
                            f'to {user.email}'
                        )
                    )

                else:

                    skipped_count += 1

                    self.stderr.write(
                        f'Email was not sent for '
                        f'"{task.title}".'
                    )

            except Exception as error:

                # One unreachable mailbox must not stop the run,
                # and reminder_sent_at stays empty so the next
                # run retries this task.

                skipped_count += 1

                self.stderr.write(
                    self.style.ERROR(
                        f'Failed to send reminder for '
                        f'"{task.title}": {error}'
                    )
                )

        if dry_run:

            self.stdout.write(
                self.style.WARNING(
                    f'Dry run complete. {sent_count} '
                    f'reminders would have been sent.'
                )
            )

        else:

            self.stdout.write(
                self.style.SUCCESS(
                    f'Total reminders sent: {sent_count}'
                )
            )

        if skipped_count:

            self.stdout.write(
                self.style.WARNING(
                    f'Total skipped or failed: {skipped_count}'
                )
            )

    def format_date(self, value):

        return value.strftime(
            '%B %d, %Y'
        ).replace(
            ' 0',
            ' '
        )
