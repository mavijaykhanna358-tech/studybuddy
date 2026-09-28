"""
Tests for the Subject / Task / Note workspace.

Covers the model helpers, the forms, and the views. The most
important group is `OwnershipIsolationTest`: every view looks up
its object with `user=request.user`, and these tests prove that a
signed in student cannot read, change or delete somebody else's
rows by editing a URL.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import NoteForm, SubjectForm, TaskForm
from .models import Note, Subject, Task


TODAY = date.today()

TOMORROW = TODAY + timedelta(days=1)

YESTERDAY = TODAY - timedelta(days=1)


# ============================================================
# HELPERS
# ============================================================

def make_user(username, password='Pass123!'):

    return get_user_model().objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password=password,
    )


# ============================================================
# MODEL TESTS
# ============================================================

class TaskModelTests(TestCase):
    def setUp(self):
        self.user = make_user('student1')

    def test_task_creation_with_expected_fields(self):
        task = Task.objects.create(
            user=self.user,
            title='Read chapter 4',
            description='Finish the reading notes before class.',
            category='Study',
            priority='High',
            status='Pending',
            due_date=TODAY + timedelta(days=2)
        )

        self.assertEqual(task.title, 'Read chapter 4')
        self.assertEqual(task.user, self.user)
        self.assertEqual(task.priority, 'High')
        self.assertEqual(task.category, 'Study')
        self.assertEqual(str(task), 'Read chapter 4')

    def test_defaults(self):
        task = Task.objects.create(
            user=self.user,
            title='Default task',
        )

        self.assertEqual(task.priority, 'Medium')
        self.assertEqual(task.status, 'Pending')
        self.assertEqual(task.category, 'General')
        self.assertIsNone(task.subject)
        self.assertIsNone(task.due_date)
        self.assertEqual(task.description, '')

    def test_completed_task_is_marked_correctly(self):
        task = Task.objects.create(
            user=self.user,
            title='Submit assignment',
            status='Completed',
            due_date=YESTERDAY
        )

        self.assertTrue(task.is_completed)

        pending = Task.objects.create(
            user=self.user,
            title='Not finished'
        )

        self.assertFalse(pending.is_completed)

    def test_is_overdue(self):
        overdue = Task.objects.create(
            user=self.user,
            title='Overdue',
            due_date=YESTERDAY
        )

        not_overdue = Task.objects.create(
            user=self.user,
            title='Due today',
            due_date=TODAY
        )

        no_date = Task.objects.create(
            user=self.user,
            title='No due date'
        )

        done = Task.objects.create(
            user=self.user,
            title='Done late',
            status='Completed',
            due_date=YESTERDAY
        )

        self.assertTrue(overdue.is_overdue)
        self.assertFalse(not_overdue.is_overdue)
        self.assertFalse(no_date.is_overdue)
        self.assertFalse(done.is_overdue)

    def test_days_until_due(self):
        task = Task.objects.create(
            user=self.user,
            title='Due in three days',
            due_date=TODAY + timedelta(days=3)
        )

        undated = Task.objects.create(
            user=self.user,
            title='No due date'
        )

        self.assertEqual(task.days_until_due, 3)
        self.assertIsNone(undated.days_until_due)

    def test_default_ordering_is_due_date_then_real_priority(self):
        # A plain ordering on the priority CharField would sort
        # alphabetically (High, Low, Medium). The model orders by
        # real urgency instead, with undated tasks last.

        low = Task.objects.create(
            user=self.user,
            title='Low',
            due_date=TODAY,
            priority='Low'
        )

        high = Task.objects.create(
            user=self.user,
            title='High',
            due_date=TODAY,
            priority='High'
        )

        medium = Task.objects.create(
            user=self.user,
            title='Medium',
            due_date=TODAY,
            priority='Medium'
        )

        undated = Task.objects.create(
            user=self.user,
            title='Undated',
            priority='High'
        )

        earlier = Task.objects.create(
            user=self.user,
            title='Earlier',
            due_date=YESTERDAY
        )

        self.assertEqual(
            list(Task.objects.all()),
            [earlier, high, medium, low, undated]
        )

    def test_changing_the_due_date_clears_the_reminder_flag(self):
        task = Task.objects.create(
            user=self.user,
            title='Reminder task',
            due_date=TODAY
        )

        Task.objects.filter(pk=task.pk).update(
            reminder_sent_at=timezone.now()
        )

        task.refresh_from_db()
        task.due_date = TOMORROW
        task.save()

        task.refresh_from_db()

        self.assertIsNone(task.reminder_sent_at)

    def test_reopening_a_completed_task_clears_the_reminder_flag(self):
        task = Task.objects.create(
            user=self.user,
            title='Reopened task',
            status='Completed',
            due_date=TOMORROW
        )

        Task.objects.filter(pk=task.pk).update(
            reminder_sent_at=timezone.now()
        )

        task.refresh_from_db()
        task.status = 'Pending'
        task.save()

        task.refresh_from_db()

        self.assertIsNone(task.reminder_sent_at)


class SubjectModelTests(TestCase):
    def test_subject_name_is_unique_per_user(self):
        user = make_user('owner')

        Subject.objects.create(
            user=user,
            name='Mathematics'
        )

        with self.assertRaises(IntegrityError):

            with transaction.atomic():

                Subject.objects.create(
                    user=user,
                    name='Mathematics'
                )

    def test_two_students_can_use_the_same_subject_name(self):
        Subject.objects.create(
            user=make_user('first'),
            name='Mathematics'
        )

        Subject.objects.create(
            user=make_user('second'),
            name='Mathematics'
        )

        self.assertEqual(Subject.objects.count(), 2)

    def test_subject_str(self):
        subject = Subject.objects.create(
            user=make_user('owner'),
            name='Physics'
        )

        self.assertEqual(str(subject), 'Physics')


class NoteModelTests(TestCase):
    def test_deleting_a_subject_keeps_its_notes(self):
        # `Note.subject` is SET_NULL so deleting a subject does not
        # silently destroy a student's notes.

        user = make_user('owner')

        subject = Subject.objects.create(
            user=user,
            name='Chemistry'
        )

        note = Note.objects.create(
            user=user,
            subject=subject,
            title='Periodic table',
            content='Groups and periods.'
        )

        subject.delete()

        note.refresh_from_db()

        self.assertIsNone(note.subject)

    def test_deleting_a_subject_deletes_its_tasks(self):
        user = make_user('owner')

        subject = Subject.objects.create(
            user=user,
            name='Biology'
        )

        Task.objects.create(
            user=user,
            subject=subject,
            title='Mitosis revision'
        )

        subject.delete()

        self.assertEqual(Task.objects.count(), 0)


# ============================================================
# FORM TESTS
# ============================================================

class SubjectFormTests(TestCase):
    def setUp(self):
        self.user = make_user('owner')

    def test_duplicate_name_is_rejected_for_the_same_user(self):
        Subject.objects.create(
            user=self.user,
            name='Mathematics'
        )

        form = SubjectForm(
            data={
                'name': '  mathematics  ',
                'description': '',
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_the_same_name_is_allowed_for_another_user(self):
        Subject.objects.create(
            user=make_user('someone_else'),
            name='Mathematics'
        )

        form = SubjectForm(
            data={
                'name': 'Mathematics',
                'description': '',
            },
            user=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_name_is_required(self):
        form = SubjectForm(
            data={
                'name': '   ',
                'description': '',
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)


class TaskFormTests(TestCase):
    def setUp(self):
        self.user = make_user('owner')

        self.subject = Subject.objects.create(
            user=self.user,
            name='Mathematics'
        )

    def test_subject_choices_are_limited_to_the_user(self):
        other_subject = Subject.objects.create(
            user=make_user('someone_else'),
            name='Their Subject'
        )

        form = TaskForm(user=self.user)

        self.assertNotIn(
            other_subject,
            form.fields['subject'].queryset
        )

    def test_another_users_subject_is_rejected_on_save(self):
        other_subject = Subject.objects.create(
            user=make_user('someone_else'),
            name='Their Subject'
        )

        form = TaskForm(
            data={
                'title': 'Borrowed subject',
                'subject': other_subject.pk,
                'priority': 'Medium',
                'status': 'Pending',
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('subject', form.errors)

    def test_past_due_date_is_rejected_for_a_new_task(self):
        form = TaskForm(
            data={
                'title': 'Backdated',
                'due_date': YESTERDAY.isoformat(),
                'priority': 'Medium',
                'status': 'Pending',
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('due_date', form.errors)

    def test_past_due_date_is_allowed_when_editing(self):
        # A task that was due yesterday should still be reschedulable
        # and savable without the form refusing to load.

        task = Task.objects.create(
            user=self.user,
            title='Overdue but real',
            due_date=YESTERDAY
        )

        form = TaskForm(
            data={
                'title': 'Overdue but real',
                'due_date': YESTERDAY.isoformat(),
                'priority': 'Medium',
                'status': 'Pending',
            },
            instance=task,
            user=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_title_is_required(self):
        form = TaskForm(
            data={
                'title': '   ',
                'priority': 'Medium',
                'status': 'Pending',
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('title', form.errors)


class NoteFormTests(TestCase):
    def setUp(self):
        self.user = make_user('owner')

    def test_content_is_required(self):
        form = NoteForm(
            data={
                'title': 'A note',
                'content': '   ',
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('content', form.errors)

    def test_disallowed_attachment_type_is_rejected(self):
        upload = SimpleUploadedFile(
            'malware.exe',
            b'MZ\x90\x00',
            content_type='application/octet-stream'
        )

        form = NoteForm(
            data={
                'title': 'A note',
                'content': 'Some content',
            },
            files={
                'attachment': upload
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('attachment', form.errors)

    def test_oversized_attachment_is_rejected(self):
        upload = SimpleUploadedFile(
            'huge.pdf',
            b'%PDF-1.4',
            content_type='application/pdf'
        )

        # Fake the size rather than allocating 25 MB in a test.

        upload.size = NoteForm.MAX_ATTACHMENT_SIZE + 1

        form = NoteForm(
            data={
                'title': 'A note',
                'content': 'Some content',
            },
            files={
                'attachment': upload
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('attachment', form.errors)

    def test_allowed_attachment_is_accepted(self):
        upload = SimpleUploadedFile(
            'revision.pdf',
            b'%PDF-1.4',
            content_type='application/pdf'
        )

        form = NoteForm(
            data={
                'title': 'A note',
                'content': 'Some content',
            },
            files={
                'attachment': upload
            },
            user=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)


# ============================================================
# SUBJECT VIEW TESTS
# ============================================================

class SubjectViewTests(TestCase):
    def setUp(self):
        self.user = make_user('owner')
        self.client.force_login(self.user)

        self.subject = Subject.objects.create(
            user=self.user,
            name='Mathematics',
            description='Counting and calculus.'
        )

    def test_list_shows_only_the_users_subjects(self):
        Subject.objects.create(
            user=make_user('someone_else'),
            name='Their Subject'
        )

        response = self.client.get(
            reverse('subjects')
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mathematics')
        self.assertNotContains(response, 'Their Subject')

    def test_list_search_filters_by_name(self):
        response = self.client.get(
            reverse('subjects'),
            {
                'q': 'math'
            }
        )

        self.assertEqual(
            list(response.context['subjects']),
            [self.subject]
        )

    def test_create_assigns_the_signed_in_user(self):
        response = self.client.post(
            reverse('subject_create'),
            {
                'name': 'Physics',
                'description': 'Motion and energy.',
            }
        )

        subject = Subject.objects.get(name='Physics')

        self.assertRedirects(
            response,
            reverse(
                'subject_detail',
                args=[subject.pk]
            )
        )

        self.assertEqual(subject.user, self.user)

    def test_duplicate_name_shows_a_form_error(self):
        response = self.client.post(
            reverse('subject_create'),
            {
                'name': 'Mathematics',
                'description': '',
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already have a subject')

        self.assertEqual(Subject.objects.count(), 1)

    def test_update_saves_changes(self):
        response = self.client.post(
            reverse(
                'subject_edit',
                args=[self.subject.pk]
            ),
            {
                'name': 'Mathematics 2',
                'description': 'Updated.',
            }
        )

        self.subject.refresh_from_db()

        self.assertRedirects(
            response,
            reverse(
                'subject_detail',
                args=[self.subject.pk]
            )
        )

        self.assertEqual(self.subject.name, 'Mathematics 2')

    def test_delete_requires_post(self):
        response = self.client.get(
            reverse(
                'subject_delete',
                args=[self.subject.pk]
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Subject.objects.count(), 1)

    def test_delete_on_post(self):
        response = self.client.post(
            reverse(
                'subject_delete',
                args=[self.subject.pk]
            )
        )

        self.assertRedirects(
            response,
            reverse('subjects')
        )

        self.assertEqual(Subject.objects.count(), 0)

    def test_delete_page_warns_about_cascade_counts(self):
        Task.objects.create(
            user=self.user,
            subject=self.subject,
            title='Algebra practice'
        )

        response = self.client.get(
            reverse(
                'subject_delete',
                args=[self.subject.pk]
            )
        )

        self.assertEqual(response.context['task_count'], 1)
        self.assertEqual(response.context['note_count'], 0)
        self.assertContains(response, '1')


# ============================================================
# TASK VIEW TESTS
# ============================================================

class TaskViewTests(TestCase):
    def setUp(self):
        self.user = make_user('owner')
        self.client.force_login(self.user)

        self.subject = Subject.objects.create(
            user=self.user,
            name='Mathematics'
        )

        self.task = Task.objects.create(
            user=self.user,
            subject=self.subject,
            title='Solve quadratics',
            due_date=TOMORROW,
            priority='High'
        )

    def test_list_shows_the_users_tasks(self):
        Task.objects.create(
            user=make_user('someone_else'),
            title='Their task'
        )

        response = self.client.get(
            reverse('tasks')
        )

        self.assertContains(response, 'Solve quadratics')
        self.assertNotContains(response, 'Their task')

    def test_list_filters_by_status(self):
        response = self.client.get(
            reverse('tasks'),
            {
                'status': 'Completed'
            }
        )

        self.assertEqual(list(response.context['tasks']), [])

    def test_invalid_filter_values_are_ignored(self):
        # A hand edited URL must not raise or filter on nonsense.

        response = self.client.get(
            reverse('tasks'),
            {
                'status': 'nonsense',
                'priority': 'nonsense',
                'due_date': 'not-a-date',
                'subject': 'abc',
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context['tasks']),
            [self.task]
        )

    def test_list_is_paginated(self):
        for index in range(12):

            Task.objects.create(
                user=self.user,
                title=f'Filler {index}'
            )

        first_page = self.client.get(
            reverse('tasks')
        )

        self.assertEqual(
            len(first_page.context['page_obj'].object_list),
            9
        )

        second_page = self.client.get(
            reverse('tasks'),
            {
                'page': 2
            }
        )

        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(
            len(second_page.context['page_obj'].object_list),
            4
        )

    def test_out_of_range_page_returns_last_page(self):
        response = self.client.get(
            reverse('tasks'),
            {
                'page': 99
            }
        )

        self.assertEqual(response.status_code, 200)

    def test_create_prefills_an_owned_subject(self):
        response = self.client.get(
            reverse('task_create'),
            {
                'subject': self.subject.pk
            }
        )

        self.assertEqual(
            response.context['form'].initial['subject'],
            self.subject.pk
        )

    def test_create_ignores_a_subject_owned_by_someone_else(self):
        other_subject = Subject.objects.create(
            user=make_user('someone_else'),
            name='Their Subject'
        )

        response = self.client.get(
            reverse('task_create'),
            {
                'subject': other_subject.pk
            }
        )

        self.assertNotIn('subject', response.context['form'].initial)

    def test_create_saves_the_task(self):
        response = self.client.post(
            reverse('task_create'),
            {
                'title': 'New task',
                'subject': self.subject.pk,
                'due_date': TOMORROW.isoformat(),
                'priority': 'Low',
                'status': 'Pending',
            }
        )

        task = Task.objects.get(title='New task')

        self.assertRedirects(
            response,
            reverse('tasks')
        )

        self.assertEqual(task.user, self.user)

    def test_create_rejects_a_foreign_subject(self):
        other_subject = Subject.objects.create(
            user=make_user('someone_else'),
            name='Their Subject'
        )

        response = self.client.post(
            reverse('task_create'),
            {
                'title': 'Sneaky task',
                'subject': other_subject.pk,
                'priority': 'Low',
                'status': 'Pending',
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Task.objects.filter(title='Sneaky task').count(), 0)

    def test_detail_page_provides_date_context(self):
        response = self.client.get(
            reverse(
                'task_detail',
                args=[self.task.pk]
            )
        )

        self.assertEqual(response.context['today'], TODAY)
        self.assertEqual(response.context['tomorrow'], TOMORROW)

    def test_delete_requires_post(self):
        response = self.client.get(
            reverse(
                'task_delete',
                args=[self.task.pk]
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Task.objects.count(), 1)

    def test_delete_on_post(self):
        response = self.client.post(
            reverse(
                'task_delete',
                args=[self.task.pk]
            )
        )

        self.assertRedirects(
            response,
            reverse('tasks')
        )

        self.assertEqual(Task.objects.count(), 0)


class TaskToggleTests(TestCase):
    def setUp(self):
        self.user = make_user('owner')
        self.client.force_login(self.user)

        self.task = Task.objects.create(
            user=self.user,
            title='Toggle me'
        )

    def test_get_does_not_change_the_task(self):
        response = self.client.get(
            reverse(
                'task_toggle',
                args=[self.task.pk]
            )
        )

        self.task.refresh_from_db()

        self.assertEqual(self.task.status, 'Pending')
        self.assertEqual(response.status_code, 302)

    def test_post_marks_the_task_completed(self):
        self.client.post(
            reverse(
                'task_toggle',
                args=[self.task.pk]
            )
        )

        self.task.refresh_from_db()

        self.assertEqual(self.task.status, 'Completed')

    def test_post_reopens_a_completed_task(self):
        self.task.status = 'Completed'
        self.task.save()

        self.client.post(
            reverse(
                'task_toggle',
                args=[self.task.pk]
            )
        )

        self.task.refresh_from_db()

        self.assertEqual(self.task.status, 'Pending')

    def test_redirects_back_to_the_next_url(self):
        response = self.client.post(
            reverse(
                'task_toggle',
                args=[self.task.pk]
            ),
            {
                'next': reverse(
                    'task_detail',
                    args=[self.task.pk]
                )
            }
        )

        self.assertEqual(
            response['Location'],
            reverse(
                'task_detail',
                args=[self.task.pk]
            )
        )

    def test_external_next_url_is_not_followed(self):
        response = self.client.post(
            reverse(
                'task_toggle',
                args=[self.task.pk]
            ),
            {
                'next': 'https://evil.example.com/'
            }
        )

        self.assertRedirects(
            response,
            reverse('tasks')
        )

    def test_toggle_of_a_foreign_task_is_a_404(self):
        foreign = Task.objects.create(
            user=make_user('someone_else'),
            title='Their task'
        )

        response = self.client.post(
            reverse(
                'task_toggle',
                args=[foreign.pk]
            )
        )

        self.assertEqual(response.status_code, 404)

        foreign.refresh_from_db()

        self.assertEqual(foreign.status, 'Pending')


# ============================================================
# NOTE VIEW TESTS
# ============================================================

class NoteViewTests(TestCase):
    def setUp(self):
        self.user = make_user('owner')
        self.client.force_login(self.user)

        self.subject = Subject.objects.create(
            user=self.user,
            name='History'
        )

        self.note = Note.objects.create(
            user=self.user,
            subject=self.subject,
            title='French Revolution',
            content='Bastille, 1789.'
        )

    def test_list_shows_the_users_notes(self):
        Note.objects.create(
            user=make_user('someone_else'),
            title='Their note',
            content='Private.'
        )

        response = self.client.get(
            reverse('notes')
        )

        self.assertContains(response, 'French Revolution')
        self.assertNotContains(response, 'Their note')

    def test_create_saves_the_note(self):
        response = self.client.post(
            reverse('note_create'),
            {
                'title': 'Second note',
                'content': 'More content.',
                'subject': self.subject.pk,
            }
        )

        note = Note.objects.get(title='Second note')

        self.assertRedirects(
            response,
            reverse('notes')
        )

        self.assertEqual(note.user, self.user)

    def test_detail_without_an_attachment_renders(self):
        # Regression test: the viewer's script block used to touch
        # `note.attachment.url` unconditionally, which raises when
        # the file field is empty.

        response = self.client.get(
            reverse(
                'note_detail',
                args=[self.note.pk]
            )
        )

        self.assertEqual(response.status_code, 200)

    def test_attachment_download_without_a_file_is_a_404(self):
        response = self.client.get(
            reverse(
                'note_attachment_download',
                args=[self.note.pk]
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_delete_requires_post(self):
        response = self.client.get(
            reverse(
                'note_delete',
                args=[self.note.pk]
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Note.objects.count(), 1)

    def test_delete_on_post(self):
        response = self.client.post(
            reverse(
                'note_delete',
                args=[self.note.pk]
            )
        )

        self.assertRedirects(
            response,
            reverse('notes')
        )

        self.assertEqual(Note.objects.count(), 0)


# ============================================================
# ACCESS CONTROL
# ============================================================

class OwnershipIsolationTest(TestCase):
    def setUp(self):
        self.owner = make_user('owner')
        self.intruder = make_user('intruder')

        self.client.force_login(self.intruder)

        self.subject = Subject.objects.create(
            user=self.owner,
            name='Owner Subject'
        )

        self.task = Task.objects.create(
            user=self.owner,
            subject=self.subject,
            title='Owner task'
        )

        self.note = Note.objects.create(
            user=self.owner,
            title='Owner note',
            content='Owner content.'
        )

    def test_foreign_detail_pages_are_404(self):
        urls = [
            ('subject_detail', self.subject.pk),
            ('task_detail', self.task.pk),
            ('note_detail', self.note.pk),
        ]

        for name, pk in urls:

            with self.subTest(url=name):

                response = self.client.get(
                    reverse(name, args=[pk])
                )

                self.assertEqual(response.status_code, 404)

    def test_foreign_edit_pages_are_404(self):
        urls = [
            ('subject_edit', self.subject.pk),
            ('task_edit', self.task.pk),
            ('note_edit', self.note.pk),
        ]

        for name, pk in urls:

            with self.subTest(url=name):

                response = self.client.get(
                    reverse(name, args=[pk])
                )

                self.assertEqual(response.status_code, 404)

    def test_foreign_delete_confirmations_are_404(self):
        urls = [
            ('subject_delete', self.subject.pk),
            ('task_delete', self.task.pk),
            ('note_delete', self.note.pk),
        ]

        for name, pk in urls:

            with self.subTest(url=name):

                self.assertEqual(
                    self.client.get(
                        reverse(name, args=[pk])
                    ).status_code,
                    404
                )

                self.assertEqual(
                    self.client.post(
                        reverse(name, args=[pk])
                    ).status_code,
                    404
                )

        self.assertEqual(Subject.objects.count(), 1)
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(Note.objects.count(), 1)


class LoginRequiredTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(
            user=make_user('owner'),
            name='Owner Subject'
        )

        self.task = Task.objects.create(
            user=self.subject.user,
            title='Owner task'
        )

        self.note = Note.objects.create(
            user=self.subject.user,
            title='Owner note',
            content='Content.'
        )

    def test_every_view_redirects_anonymous_users(self):
        targets = [
            ('dashboard', None),
            ('subjects', None),
            ('subject_create', None),
            ('subject_detail', self.subject.pk),
            ('subject_edit', self.subject.pk),
            ('subject_delete', self.subject.pk),
            ('tasks', None),
            ('task_create', None),
            ('task_detail', self.task.pk),
            ('task_edit', self.task.pk),
            ('task_delete', self.task.pk),
            ('task_toggle', self.task.pk),
            ('notes', None),
            ('note_create', None),
            ('note_detail', self.note.pk),
            ('note_edit', self.note.pk),
            ('note_delete', self.note.pk),
            ('note_attachment_download', self.note.pk),
            ('search', None),
        ]

        for name, pk in targets:

            with self.subTest(url=name):

                url = (
                    reverse(name)
                    if pk is None
                    else reverse(name, args=[pk])
                )

                response = self.client.get(url)

                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response['Location'])

    def test_post_only_views_do_not_change_state_when_anonymous(self):
        response = self.client.post(
            reverse(
                'task_toggle',
                args=[self.task.pk]
            )
        )

        self.task.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.task.status, 'Pending')


class GlobalSearchTests(TestCase):
    def setUp(self):
        self.user = make_user('searcher')

        self.subject = Subject.objects.create(
            user=self.user,
            name='Alchemy',
            description='Transmutation basics'
        )

        self.task = Task.objects.create(
            user=self.user,
            subject=self.subject,
            title='Brew the elixir',
            description='Follow the recipe'
        )

        self.note = Note.objects.create(
            user=self.user,
            subject=self.subject,
            title='Elixir notes',
            content='Careful with the ingredients'
        )

        self.other = make_user('someone-else')

        Subject.objects.create(
            user=self.other,
            name='Alchemy for others'
        )

        Task.objects.create(
            user=self.other,
            title='Somebody elses elixir'
        )

        Note.objects.create(
            user=self.other,
            title='Not my elixir',
            content='Private.'
        )

    def search(self, query):
        return self.client.get(
            reverse('search'),
            {'q': query},
        )

    def test_no_query_renders_the_empty_form(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('search'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], 0)

    def test_a_query_finds_both_matching_kinds(self):
        self.client.force_login(self.user)

        response = self.search('elixir')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], 2)
        self.assertContains(response, 'Brew the elixir')
        self.assertContains(response, 'Elixir notes')

    def test_a_query_can_find_all_three_kinds_at_once(self):
        self.client.force_login(self.user)

        Task.objects.filter(pk=self.task.pk).update(
            title='Alchemy: brew the elixir'
        )

        Note.objects.create(
            user=self.user,
            title='Alchemy revision',
            content='Elixir and transmutation together.'
        )

        response = self.search('alchemy')

        self.assertEqual(response.context['total'], 3)
        self.assertContains(response, 'Alchemy')
        self.assertContains(response, 'Alchemy revision')

    def test_search_is_case_insensitive(self):
        self.client.force_login(self.user)

        response = self.search('ELIXIR')

        self.assertEqual(response.context['total'], 2)

    def test_subject_descriptions_are_searchable(self):
        self.client.force_login(self.user)

        response = self.search('transmutation')

        self.assertEqual(response.context['total'], 1)
        self.assertContains(response, 'Alchemy')

    def test_note_bodies_are_searchable(self):
        self.client.force_login(self.user)

        response = self.search('ingredients')

        self.assertEqual(response.context['total'], 1)
        self.assertContains(response, 'Elixir notes')

    def test_task_descriptions_are_searchable(self):
        self.client.force_login(self.user)

        response = self.search('recipe')

        self.assertEqual(response.context['total'], 1)
        self.assertContains(response, 'Brew the elixir')

    def test_another_users_rows_are_never_returned(self):
        self.client.force_login(self.user)

        response = self.search('elixir')

        self.assertNotContains(response, 'Somebody elses elixir')
        self.assertNotContains(response, 'Not my elixir')
        self.assertNotContains(response, 'Alchemy for others')

    def test_no_match_says_so(self):
        self.client.force_login(self.user)

        response = self.search('zzzznothing')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], 0)
        self.assertContains(response, 'Nothing in your library matches')

    def test_results_are_capped_at_five_per_kind(self):
        self.client.force_login(self.user)

        for index in range(9):
            Task.objects.create(
                user=self.user,
                title=f'Extra elixir {index}'
            )

        response = self.search('elixir')

        self.assertEqual(
            response.context['results']['tasks'].count(),
            5,
        )

    def test_the_top_bar_search_links_here(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('dashboard'))

        self.assertContains(
            response,
            f'action="{reverse("search")}"',
        )
