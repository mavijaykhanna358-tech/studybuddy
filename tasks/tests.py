from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Task


class TaskModelTests(TestCase):
    def test_task_creation_with_expected_fields(self):
        user = get_user_model().objects.create_user(
            username='student1',
            email='student1@example.com',
            password='securepass123'
        )

        task = Task.objects.create(
            user=user,
            title='Read chapter 4',
            description='Finish the reading notes before class.',
            category='Study',
            priority='High',
            status='Pending',
            due_date=date.today() + timedelta(days=2)
        )

        self.assertEqual(task.title, 'Read chapter 4')
        self.assertEqual(task.user, user)
        self.assertEqual(task.priority, 'High')
        self.assertEqual(task.category, 'Study')
        self.assertEqual(str(task), 'Read chapter 4')

    def test_completed_task_is_marked_correctly(self):
        user = get_user_model().objects.create_user(
            username='student2',
            email='student2@example.com',
            password='securepass123'
        )

        task = Task.objects.create(
            user=user,
            title='Submit assignment',
            description='Upload the completed assignment.',
            category='Assignment',
            priority='Medium',
            status='Completed',
            due_date=date.today() - timedelta(days=1)
        )

        self.assertEqual(task.status, 'Completed')
        self.assertTrue(task.is_completed)
