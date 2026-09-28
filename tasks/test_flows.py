"""End to end checks for the flows a real student walks through.

The other test modules cover models, forms and individual views in
isolation. These walk whole journeys the way the browser does, so a
break in the wiring between two correct halves still fails a test.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .models import Note, Subject, Task
from .views import TASK_ORDER


User = get_user_model()


PASSWORD = 'Str0ng-Pass!42'
TODAY = date.today()


class JourneyTestCase(TestCase):

    # One signed in account, shared by most of the tests below.

    def setUp(self):

        self.user = User.objects.create_user(
            username='alice',
            email='alice@example.com',
            password=PASSWORD,
        )

        self.client.force_login(self.user)

    def make_subject(self, name='Mathematics'):

        response = self.client.post(
            reverse('subject_create'),
            {'name': name, 'description': 'Numbers'},
        )

        self.assertEqual(response.status_code, 302)

        return Subject.objects.get(name=name)


class SignUpAndSignIn(JourneyTestCase):

    def test_register_then_login_reaches_the_dashboard(self):

        response = self.client.post(reverse('register'), {
            'username': 'newbie',
            'email': 'newbie@example.com',
            'password1': PASSWORD,
            'password2': PASSWORD,
        })

        self.assertRedirects(
            response,
            reverse('login'),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            User.objects.filter(username='newbie').exists()
        )

        response = self.client.post(reverse('login'), {
            'username': 'newbie',
            'password': PASSWORD,
        })

        self.assertRedirects(
            response,
            reverse('dashboard'),
            fetch_redirect_response=False,
        )

    def test_duplicate_username_and_email_are_refused(self):

        response = self.client.post(reverse('register'), {
            'username': 'alice',
            'email': 'other@example.com',
            'password1': PASSWORD,
            'password2': PASSWORD,
        })

        self.assertContains(response, 'already taken')

        response = self.client.post(reverse('register'), {
            'username': 'someone',
            'email': 'ALICE@example.com',
            'password1': PASSWORD,
            'password2': PASSWORD,
        })

        self.assertContains(response, 'already exists')

    def test_signing_out_locks_the_pages_again(self):

        self.assertEqual(
            self.client.get(reverse('dashboard')).status_code,
            200,
        )

        self.client.post(reverse('logout'))

        response = self.client.get(reverse('dashboard'))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('dashboard')}",
            fetch_redirect_response=False,
        )


class AnonymousVisitorTest(TestCase):

    # Every signed in page has to send an anonymous visitor to the
    # login form rather than rendering it.

    def test_every_protected_page_redirects_to_login(self):

        names = [
            'dashboard', 'subjects', 'subject_create', 'tasks',
            'task_create', 'notes', 'note_create', 'search', 'profile',
        ]

        for name in names:

            with self.subTest(page=name):

                response = self.client.get(reverse(name))

                self.assertEqual(response.status_code, 302)
                self.assertIn('/login/', response.url)

    def test_posting_to_a_protected_page_is_refused_too(self):

        response = self.client.post(
            reverse('task_create'),
            {'title': 'Should not be saved', 'priority': 'Low'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)


class SubjectJourney(JourneyTestCase):

    def test_add_view_edit_search_and_delete(self):

        subject = self.make_subject('Mathematics')

        self.assertContains(
            self.client.get(reverse('subject_detail', args=[subject.pk])),
            'Mathematics',
        )

        self.client.post(reverse('subject_edit', args=[subject.pk]), {
            'name': 'Mathematics II',
            'description': 'Renamed',
        })

        subject.refresh_from_db()

        self.assertEqual(subject.name, 'Mathematics II')

        self.assertContains(
            self.client.get(reverse('subjects'), {'q': 'Mathem'}),
            'Mathematics II',
        )
        self.assertNotContains(
            self.client.get(reverse('subjects'), {'q': 'nothing here'}),
            'Mathematics II',
        )

        self.client.post(reverse('subject_delete', args=[subject.pk]))

        self.assertFalse(
            Subject.objects.filter(pk=subject.pk).exists()
        )
        self.assertNotContains(
            self.client.get(reverse('subjects')), 'Mathematics II',
        )

    def test_the_same_name_cannot_be_used_twice(self):

        self.make_subject('Physics')

        response = self.client.post(
            reverse('subject_create'),
            {'name': '  physics  '},
        )

        self.assertContains(response, 'already have a subject')

    def test_deleting_a_subject_removes_its_tasks_but_keeps_its_notes(self):

        subject = self.make_subject('History')
        task = Task.objects.create(
            user=self.user, title='Essay', subject=subject,
            status='Pending',
        )
        note = Note.objects.create(
            user=self.user, title='Sources', content='x', subject=subject,
        )

        self.client.post(reverse('subject_delete', args=[subject.pk]))

        self.assertFalse(Task.objects.filter(pk=task.pk).exists())
        # Notes keep existing with the subject cleared, so a student
        # does not lose writing by tidying up a subject.
        note.refresh_from_db()
        self.assertIsNone(note.subject_id)


class TaskJourney(JourneyTestCase):

    def test_add_edit_complete_and_delete(self):

        subject = self.make_subject('Physics')

        response = self.client.post(reverse('task_create'), {
            'title': 'Solve integrals',
            'description': 'Chapter 4',
            'subject': subject.pk,
            'priority': 'High',
            'status': 'Pending',
            'due_date': str(TODAY + timedelta(days=3)),
        })

        self.assertRedirects(
            response, reverse('tasks'), fetch_redirect_response=False,
        )

        task = Task.objects.get(title='Solve integrals')

        self.assertEqual(task.user, self.user)
        self.assertEqual(task.priority, 'High')

        self.client.post(reverse('task_edit', args=[task.pk]), {
            'title': 'Solve integrals v2',
            'subject': subject.pk,
            'priority': 'Medium',
            'status': 'Pending',
            'due_date': str(TODAY + timedelta(days=5)),
        })

        task.refresh_from_db()

        self.assertEqual(task.title, 'Solve integrals v2')
        self.assertEqual(task.priority, 'Medium')

        # Completing, then reopening, is a single POST endpoint and a
        # plain link must not be able to trigger it.
        response = self.client.get(reverse('task_toggle', args=[task.pk]))

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, 'Pending')

        self.client.post(reverse('task_toggle', args=[task.pk]))
        task.refresh_from_db()
        self.assertTrue(task.is_completed)

        self.client.post(reverse('task_toggle', args=[task.pk]))
        task.refresh_from_db()
        self.assertEqual(task.status, 'Pending')

        self.client.post(reverse('task_delete', args=[task.pk]))

        self.assertFalse(Task.objects.filter(pk=task.pk).exists())

    def test_a_new_task_cannot_be_dated_in_the_past(self):

        response = self.client.post(reverse('task_create'), {
            'title': 'Backdated',
            'priority': 'Low',
            'status': 'Pending',
            'due_date': str(TODAY - timedelta(days=2)),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cannot be before today')

    def test_the_default_order_puts_urgent_first_and_undated_last(self):

        subject = self.make_subject('Ordering')
        due = TODAY + timedelta(days=1)

        # High and Medium share a due date, so only the priority
        # ordering can separate them. Low is added to make sure it
        # sorts after both rather than alphabetically before Medium.
        medium = Task.objects.create(
            user=self.user, title='ZZ medium', priority='Medium',
            status='Pending', due_date=due, subject=subject,
        )
        high = Task.objects.create(
            user=self.user, title='ZZ high', priority='High',
            status='Pending', due_date=due, subject=subject,
        )
        low = Task.objects.create(
            user=self.user, title='ZZ low', priority='Low',
            status='Pending', due_date=due, subject=subject,
        )
        undated = Task.objects.create(
            user=self.user, title='ZZ undated', priority='High',
            status='Pending', due_date=None, subject=subject,
        )

        listed = list(Task.objects.filter(
            user=self.user, title__startswith='ZZ ',
        ).order_by(*TASK_ORDER))

        self.assertEqual(
            listed, [high, medium, low, undated],
            'High must precede Medium and Low, and the undated task '
            'must come last.',
        )

    def test_sorting_by_priority_also_beats_the_alphabetical_order(self):

        due = TODAY + timedelta(days=1)

        medium = Task.objects.create(
            user=self.user, title='PP medium', priority='Medium',
            status='Pending', due_date=due,
        )
        high = Task.objects.create(
            user=self.user, title='PP high', priority='High',
            status='Pending', due_date=due,
        )

        response = self.client.get(reverse('tasks'), {
            'q': 'PP ', 'sort': 'priority',
        })

        body = response.content.decode()

        self.assertLess(
            body.index('PP high'),
            body.index('PP medium'),
            'sort=priority fell back to alphabetical order, which '
            'puts Low before Medium',
        )
        self.assertTrue(medium.pk and high.pk)

    def test_hostile_query_parameters_do_not_break_the_list(self):

        for params in (
            {'status': "'; DROP TABLE tasks_task; --"},
            {'priority': 'urgent'},
            {'subject': 'not-a-number'},
            {'subject': '99999'},
            {'due_date': '31/12/2026'},
            {'sort': '../../etc/passwd'},
            {'page': 'not-a-page'},
        ):

            with self.subTest(params=params):

                response = self.client.get(reverse('tasks'), params)

                self.assertEqual(response.status_code, 200)


class NoteJourney(JourneyTestCase):

    def test_add_upload_download_edit_and_delete(self):

        subject = self.make_subject('Biology')

        response = self.client.post(reverse('note_create'), {
            'title': 'Cell division',
            'content': 'Mitosis and meiosis notes.',
            'subject': subject.pk,
            'attachment': SimpleUploadedFile(
                'sheet.pdf', b'%PDF-1.4 notes',
                content_type='application/pdf',
            ),
        })

        self.assertRedirects(
            response, reverse('notes'), fetch_redirect_response=False,
        )

        note = Note.objects.get(title='Cell division')

        self.assertTrue(note.attachment)

        response = self.client.get(
            reverse('note_attachment_download', args=[note.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'attachment', response.headers.get('Content-Disposition', ''),
        )

        self.client.post(reverse('note_edit', args=[note.pk]), {
            'title': 'Cell division v2',
            'content': 'Updated notes.',
            'subject': subject.pk,
        })

        note.refresh_from_db()

        self.assertEqual(note.title, 'Cell division v2')

        self.client.post(reverse('note_delete', args=[note.pk]))

        self.assertFalse(Note.objects.filter(pk=note.pk).exists())

    def test_a_note_with_no_attachment_404s_on_download(self):

        note = Note.objects.create(
            user=self.user, title='No file', content='x',
        )

        response = self.client.get(
            reverse('note_attachment_download', args=[note.pk]),
        )

        self.assertEqual(response.status_code, 404)

    def test_a_disallowed_file_type_is_refused(self):

        response = self.client.post(reverse('note_create'), {
            'title': 'Bad upload',
            'content': 'x',
            'attachment': SimpleUploadedFile(
                'payload.exe', b'MZ', content_type='application/x-msdownload',
            ),
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not supported')

    def test_a_blank_note_is_refused(self):

        response = self.client.post(reverse('note_create'), {
            'title': 'No body', 'content': '   ',
        })

        self.assertEqual(response.status_code, 200)


class SearchJourney(JourneyTestCase):

    def test_one_query_finds_a_subject_a_task_and_a_note(self):

        self.make_subject('Astronomy')

        self.client.post(reverse('task_create'), {
            'title': 'Telescope alignment',
            'priority': 'Low', 'status': 'Pending',
        })
        self.client.post(reverse('note_create'), {
            'title': 'Lunar phases',
            'content': 'Something about the moon.',
        })

        response = self.client.get(reverse('search'), {'q': 'a'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Astronomy')

        response = self.client.get(reverse('search'), {'q': 'telescope'})

        self.assertContains(response, 'Telescope alignment')

        response = self.client.get(reverse('search'), {'q': 'moon'})

        self.assertContains(response, 'Lunar phases')

    def test_search_with_no_query_renders(self):

        self.assertEqual(
            self.client.get(reverse('search')).status_code, 200,
        )


class OneAccountCannotReachAnother(JourneyTestCase):

    def setUp(self):

        super().setUp()

        self.other = User.objects.create_user(
            username='mallory',
            email='mallory@example.com',
            password=PASSWORD,
        )

    def test_every_detail_edit_and_delete_url_is_404_for_others(self):

        subject = self.make_subject('Private notes')
        task = Task.objects.create(
            user=self.user, title='Private task', status='Pending',
        )
        note = Note.objects.create(
            user=self.user, title='Private note', content='x',
        )

        urls = [
            reverse('subject_detail', args=[subject.pk]),
            reverse('subject_edit', args=[subject.pk]),
            reverse('subject_delete', args=[subject.pk]),
            reverse('task_detail', args=[task.pk]),
            reverse('task_edit', args=[task.pk]),
            reverse('task_delete', args=[task.pk]),
            reverse('task_toggle', args=[task.pk]),
            reverse('note_detail', args=[note.pk]),
            reverse('note_edit', args=[note.pk]),
            reverse('note_delete', args=[note.pk]),
        ]

        self.client.force_login(self.other)

        for url in urls:

            with self.subTest(url=url):

                self.assertEqual(
                    self.client.get(url).status_code, 404,
                )
                self.assertEqual(
                    self.client.post(url, {
                        'title': 'hijacked', 'name': 'hijacked',
                        'content': 'hijacked', 'priority': 'Low',
                        'status': 'Pending',
                    }).status_code,
                    404,
                )

    def test_another_accounts_subject_cannot_be_attached_to_a_task(self):

        subject = self.make_subject('Not yours')
        self.client.force_login(self.other)

        response = self.client.post(reverse('task_create'), {
            'title': 'Borrowed subject',
            'priority': 'Low',
            'status': 'Pending',
            'subject': subject.pk,
        })

        self.assertEqual(response.status_code, 200)

        self.assertFalse(Task.objects.filter(title='Borrowed subject').exists())

    def test_lists_and_search_never_leak_another_accounts_rows(self):

        subject = self.make_subject('Hidden subject')
        self.client.post(reverse('task_create'), {
            'title': 'Hidden task', 'priority': 'Low', 'status': 'Pending',
        })
        self.client.post(reverse('note_create'), {
            'title': 'Hidden note', 'content': 'hiddenbody',
        })

        self.client.force_login(self.other)

        self.assertNotContains(
            self.client.get(reverse('subjects')), 'Hidden subject',
        )
        self.assertNotContains(
            self.client.get(reverse('tasks')), 'Hidden task',
        )
        self.assertNotContains(
            self.client.get(reverse('notes')), 'Hidden note',
        )
        self.assertNotContains(
            self.client.get(reverse('search'), {'q': 'Hidden'}),
            'Hidden task',
        )
        self.assertNotContains(
            self.client.get(reverse('search'), {'q': 'hiddenbody'}),
            'Hidden note',
        )
        self.assertNotContains(
            self.client.get(reverse('dashboard')), 'Hidden subject',
        )
        self.assertEqual(subject.user, self.user)


class ForgotPasswordJourney(TestCase):

    def setUp(self):

        self.user = User.objects.create_user(
            username='forgetful',
            email='forgetful@example.com',
            password=PASSWORD,
        )

        mail.outbox = []

    def test_reset_link_sets_a_working_new_password(self):

        response = self.client.post(
            reverse('password_reset'),
            {'email': 'forgetful@example.com'},
        )

        self.assertRedirects(
            response,
            reverse('password_reset_done'),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)

        body = mail.outbox[0].body

        self.assertIn('/reset/', body)

        start = body.index('http')
        link = body[start:].split()[0].strip().rstrip('.')
        link = link.split('testserver', 1)[-1] if 'testserver' in link else link
        link = link.split('example.com', 1)[-1]

        # Django sends an account holder with an existing password to a
        # separate set-password step, so follow the chain.
        response = self.client.get(link, follow=True)

        self.assertEqual(response.status_code, 200)

        final = response.redirect_chain[-1][0] if response.redirect_chain \
            else link

        response = self.client.post(final, {
            'new_password1': 'N3w-Pass!99',
            'new_password2': 'N3w-Pass!99',
        })

        self.assertRedirects(
            response, reverse('login'), fetch_redirect_response=False,
        )

        fresh = Client()

        response = fresh.post(reverse('login'), {
            'username': 'forgetful', 'password': 'N3w-Pass!99',
        })

        self.assertRedirects(
            response, reverse('dashboard'), fetch_redirect_response=False,
        )

        stale = Client()

        stale.post(reverse('login'), {
            'username': 'forgetful', 'password': PASSWORD,
        })

        self.assertNotIn('_auth_user_id', stale.session)

    def test_an_unknown_address_sends_nothing(self):

        self.client.post(
            reverse('password_reset'),
            {'email': 'nobody@nowhere.test'},
        )

        self.assertEqual(len(mail.outbox), 0)


class EmptyAccountJourney(TestCase):

    # A brand new account sees only empty states, which are a different
    # layout from the populated pages and are easy to leave broken.

    def setUp(self):

        User.objects.create_user(
            username='fresh', email='fresh@example.com', password=PASSWORD,
        )

        self.client.login(username='fresh', password=PASSWORD)

    def test_every_page_renders_with_no_data(self):

        for name in (
            'dashboard', 'subjects', 'tasks', 'notes', 'profile',
            'task_create', 'note_create', 'subject_create',
        ):

            with self.subTest(page=name):

                self.assertEqual(
                    self.client.get(reverse(name)).status_code, 200,
                )

    def test_search_with_no_matches_renders(self):

        self.assertEqual(
            self.client.get(reverse('search'), {'q': 'zzz'}).status_code,
            200,
        )


class PagingJourney(JourneyTestCase):

    def test_a_page_number_past_the_end_still_renders(self):

        for i in range(12):

            Task.objects.create(
                user=self.user, title=f'Task {i}',
                status='Pending', due_date=TODAY + timedelta(days=i + 1),
            )

        self.assertEqual(
            self.client.get(reverse('tasks'), {'page': 1}).status_code, 200,
        )
        self.assertEqual(
            self.client.get(reverse('tasks'), {'page': 99}).status_code, 200,
        )
        self.assertEqual(
            self.client.get(reverse('tasks'), {'page': 'x'}).status_code, 200,
        )

