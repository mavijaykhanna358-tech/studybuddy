from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone

from tasks.models import Task


class Command(BaseCommand):

    help = 'Send email reminders for tasks due tomorrow.'

    def handle(self, *args, **options):

        today = timezone.localdate()

        tomorrow = today + timezone.timedelta(
            days=1
        )

        tasks = Task.objects.filter(
            due_date=tomorrow
        ).exclude(
            status='Completed'
        ).select_related(
            'user',
            'subject'
        )

        sent_count = 0

        for task in tasks:

            user = task.user

            if not user.email:
                self.stdout.write(
                    self.style.WARNING(
                        f'Skipped "{task.title}" - '
                        f'user has no email address.'
                    )
                )
                continue

            subject_name = ''

            if task.subject:
                subject_name = task.subject.name

            email_subject = (
                f'Task Reminder: {task.title} is due tomorrow'
            )

            email_message = f"""
Hello {user.username},

This is a reminder that your task is due tomorrow.

Task: {task.title}
"""

            if subject_name:

                email_message += f"""
Subject: {subject_name}
"""

            email_message += f"""
Due date: {task.due_date.strftime('%B %d, %Y')}

Tomorrow is the last day to finish this task.

Please complete it before the due date.

Regards,
StudyBuddy
"""

            try:

                send_mail(
                    subject=email_subject,
                    message=email_message,
                    from_email=None,
                    recipient_list=[
                        user.email
                    ],
                    fail_silently=False
                )

                sent_count += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f'Reminder sent for "{task.title}" '
                        f'to {user.email}'
                    )
                )

            except Exception as e:

                self.stdout.write(
                    self.style.ERROR(
                        f'Failed to send reminder for '
                        f'"{task.title}": {e}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Total reminders sent: {sent_count}'
            )
        )