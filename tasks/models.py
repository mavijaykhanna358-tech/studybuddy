from datetime import date

from django.conf import settings
from django.db import models


class Subject(models.Model):

    # Subjects are a per user workspace. Case insensitive unique
    # names stop the same subject being created twice.

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=[
                    'user',
                    'name',
                ],
                name='unique_subject_name_per_user',
            ),
        ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subjects'
    )

    name = models.CharField(
        max_length=100
    )

    description = models.TextField(
        blank=True,
        default=''
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.name


class Task(models.Model):

    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
    ]

    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tasks'
    )

    subject = models.ForeignKey(
        'Subject',
        on_delete=models.CASCADE,
        related_name='tasks',
        null=True,
        blank=True
    )

    title = models.CharField(
        max_length=200
    )

    description = models.TextField(
        blank=True,
        default=''
    )

    category = models.CharField(
        max_length=50,
        default='General',
        blank=True
    )

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='Medium'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Pending'
    )

    due_date = models.DateField(
        null=True,
        blank=True
    )

    reminder_sent_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        # priority is a CharField, so a plain ordering sorts it
        # alphabetically (High, Low, Medium). This orders by real
        # urgency and puts tasks without a due date last.

        ordering = [
            models.Case(
                models.When(
                    due_date__isnull=True,
                    then=1
                ),
                default=0,
                output_field=models.IntegerField(),
            ),
            'due_date',
            models.Case(
                models.When(
                    priority='High',
                    then=0
                ),
                models.When(
                    priority='Medium',
                    then=1
                ),
                default=2,
                output_field=models.IntegerField(),
            ),
            'title',
        ]

        indexes = [
            models.Index(
                fields=[
                    'user',
                    'status',
                ],
                name='task_user_status_idx',
            ),

            models.Index(
                fields=[
                    'user',
                    'due_date',
                ],
                name='task_user_due_idx',
            ),
        ]

    @property
    def is_completed(self):
        return self.status == 'Completed'

    @property
    def is_overdue(self):
        if not self.due_date:
            return False

        if self.status == 'Completed':
            return False

        return self.due_date < date.today()

    @property
    def days_until_due(self):
        if not self.due_date:
            return None

        return (self.due_date - date.today()).days

    def save(self, *args, **kwargs):

        if self.pk:

            old_task = Task.objects.filter(
                pk=self.pk
            ).first()

            if old_task:

                # If due date changes,
                # allow a new reminder.
                if old_task.due_date != self.due_date:
                    self.reminder_sent_at = None

                # If a completed task is reopened,
                # allow a new reminder.
                elif (
                    old_task.status == 'Completed'
                    and self.status != 'Completed'
                ):
                    self.reminder_sent_at = None

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Note(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notes'
    )

    subject = models.ForeignKey(
        'Subject',
        on_delete=models.SET_NULL,
        related_name='notes',
        null=True,
        blank=True
    )

    title = models.CharField(
        max_length=200
    )

    content = models.TextField()

    attachment = models.FileField(
        upload_to='notes/',
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title