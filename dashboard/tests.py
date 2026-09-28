"""
Tests for the dashboard.

`get_dashboard_stats` is the single place that computes the
numbers on the dashboard, so it is tested directly instead of
being re-derived from the rendered page.
"""

import calendar as calendar_module

from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from tasks.models import Note, Subject, Task

from .context_processors import studybuddy_context
from .views import (
    get_dashboard_stats,
    get_month_calendar,
    get_notifications,
    get_study_streak,
    get_subject_progress,
)


TODAY = date.today()

TOMORROW = TODAY + timedelta(days=1)

YESTERDAY = TODAY - timedelta(days=1)


def make_user(username):

    return get_user_model().objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='Pass123!',
    )


def make_task(user, **overrides):
    defaults = {
        'user': user,
        'title': 'A task',
    }

    defaults.update(overrides)

    return Task.objects.create(**defaults)


class DashboardStatsTests(TestCase):
    def setUp(self):
        self.user = make_user('student')

    def test_empty_workspace_reports_zeroes(self):
        stats = get_dashboard_stats(self.user)

        self.assertEqual(stats['total_subjects'], 0)
        self.assertEqual(stats['total_tasks'], 0)
        self.assertEqual(stats['completed_tasks'], 0)
        self.assertEqual(stats['pending_tasks'], 0)
        self.assertEqual(stats['in_progress_tasks'], 0)
        self.assertEqual(stats['total_notes'], 0)
        self.assertEqual(stats['completion_percentage'], 0)
        self.assertEqual(stats['overdue_tasks'], 0)
        self.assertEqual(stats['due_soon_tasks'], 0)
        self.assertEqual(stats['high_priority_tasks'], 0)
        self.assertEqual(list(stats['upcoming_tasks']), [])
        self.assertEqual(list(stats['recent_notes']), [])

    def test_counts_are_limited_to_the_signed_in_user(self):
        other = make_user('other')

        make_task(other, title='Not mine')
        make_task(self.user, title='Mine')

        stats = get_dashboard_stats(self.user)

        self.assertEqual(stats['total_tasks'], 1)

    def test_status_counts(self):
        make_task(self.user, title='Pending one')
        make_task(self.user, title='Pending two')
        make_task(self.user, title='Working', status='In Progress')
        make_task(self.user, title='Done', status='Completed')

        stats = get_dashboard_stats(self.user)

        self.assertEqual(stats['total_tasks'], 4)
        self.assertEqual(stats['pending_tasks'], 2)
        self.assertEqual(stats['in_progress_tasks'], 1)
        self.assertEqual(stats['completed_tasks'], 1)
        self.assertEqual(stats['completion_percentage'], 25)

    def test_completion_percentage_is_rounded(self):
        make_task(self.user, title='Done', status='Completed')
        make_task(self.user, title='Pending')
        make_task(self.user, title='Pending')

        stats = get_dashboard_stats(self.user)

        self.assertEqual(stats['completion_percentage'], 33)

    def test_overdue_excludes_completed_and_undated_tasks(self):
        make_task(self.user, title='Late', due_date=YESTERDAY)
        make_task(
            self.user,
            title='Late but done',
            due_date=YESTERDAY,
            status='Completed'
        )
        make_task(self.user, title='No due date')

        stats = get_dashboard_stats(self.user)

        self.assertEqual(stats['overdue_tasks'], 1)

    def test_due_soon_covers_today_and_tomorrow(self):
        make_task(self.user, title='Today', due_date=TODAY)
        make_task(self.user, title='Tomorrow', due_date=TOMORROW)
        make_task(
            self.user,
            title='Today but done',
            due_date=TODAY,
            status='Completed'
        )
        make_task(
            self.user,
            title='Later',
            due_date=TODAY + timedelta(days=7)
        )

        stats = get_dashboard_stats(self.user)

        self.assertEqual(stats['due_soon_tasks'], 2)

    def test_high_priority_excludes_completed(self):
        make_task(self.user, title='Urgent', priority='High')
        make_task(self.user, title='Normal', priority='Medium')
        make_task(
            self.user,
            title='Urgent but done',
            priority='High',
            status='Completed'
        )

        stats = get_dashboard_stats(self.user)

        self.assertEqual(stats['high_priority_tasks'], 1)

    def test_upcoming_tasks_are_the_five_nearest_and_unfinished(self):
        for days in range(1, 8):

            make_task(
                self.user,
                title=f'In {days} days',
                due_date=TODAY + timedelta(days=days)
            )

        make_task(
            self.user,
            title='In the past',
            due_date=YESTERDAY
        )

        make_task(
            self.user,
            title='Done tomorrow',
            due_date=TOMORROW,
            status='Completed'
        )

        stats = get_dashboard_stats(self.user)

        titles = [
            task.title
            for task in stats['upcoming_tasks']
        ]

        self.assertEqual(
            titles,
            [
                'In 1 days',
                'In 2 days',
                'In 3 days',
                'In 4 days',
                'In 5 days',
            ]
        )

    def test_recent_notes_are_the_five_most_recently_updated(self):
        subject = Subject.objects.create(
            user=self.user,
            name='History'
        )

        for index in range(7):

            note = Note.objects.create(
                user=self.user,
                subject=subject,
                title=f'Note {index}',
                content='Content.'
            )

            Note.objects.filter(pk=note.pk).update(
                updated_at=(
                    timezone.now()
                    - timedelta(minutes=index)
                )
            )

        stats = get_dashboard_stats(self.user)

        self.assertEqual(
            [note.title for note in stats['recent_notes']],
            [
                'Note 0',
                'Note 1',
                'Note 2',
                'Note 3',
                'Note 4',
            ]
        )

    def test_today_and_tomorrow_are_exposed_for_the_template(self):
        stats = get_dashboard_stats(self.user)

        self.assertEqual(stats['today'], TODAY)
        self.assertEqual(stats['tomorrow'], TOMORROW)


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = make_user('student')

    def test_dashboard_requires_login(self):
        response = self.client.get(
            reverse('dashboard')
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_dashboard_renders_for_a_signed_in_user(self):
        self.client.force_login(self.user)

        make_task(
            self.user,
            title='Visible task',
            due_date=TOMORROW
        )

        response = self.client.get(
            reverse('dashboard')
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Visible task')

    def test_dashboard_does_not_leak_another_users_data(self):
        self.client.force_login(self.user)

        make_task(
            make_user('other'),
            title='Hidden task',
            due_date=TOMORROW
        )

        response = self.client.get(
            reverse('dashboard')
        )

        self.assertNotContains(response, 'Hidden task')


class SubjectProgressTests(TestCase):
    def setUp(self):
        self.user = make_user('student')

    def test_a_subject_without_tasks_is_kept_at_zero(self):
        subject = Subject.objects.create(
            user=self.user,
            name='Empty Subject'
        )

        rows = get_subject_progress(self.user)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['subject'], subject)
        self.assertEqual(rows[0]['total'], 0)
        self.assertEqual(rows[0]['done'], 0)
        self.assertEqual(rows[0]['percentage'], 0)

    def test_percentage_comes_from_real_task_counts(self):
        subject = Subject.objects.create(
            user=self.user,
            name='Half Done'
        )

        make_task(
            self.user,
            subject=subject,
            title='Done one',
            status='Completed'
        )

        make_task(
            self.user,
            subject=subject,
            title='Still open'
        )

        rows = get_subject_progress(self.user)

        self.assertEqual(rows[0]['total'], 2)
        self.assertEqual(rows[0]['done'], 1)
        self.assertEqual(rows[0]['left'], 1)
        self.assertEqual(rows[0]['percentage'], 50)

    def test_progress_is_per_subject_not_workspace_wide(self):
        first = Subject.objects.create(
            user=self.user,
            name='First'
        )

        second = Subject.objects.create(
            user=self.user,
            name='Second'
        )

        make_task(
            self.user,
            subject=first,
            title='Done',
            status='Completed'
        )

        make_task(
            self.user,
            subject=second,
            title='Open one'
        )

        make_task(
            self.user,
            subject=second,
            title='Open two'
        )

        rows = {
            row['subject'].name: row
            for row in get_subject_progress(self.user)
        }

        self.assertEqual(rows['First']['percentage'], 100)
        self.assertEqual(rows['Second']['percentage'], 0)

    def test_another_users_subjects_are_excluded(self):
        Subject.objects.create(
            user=make_user('other'),
            name='Theirs'
        )

        self.assertEqual(get_subject_progress(self.user), [])


class StudyStreakTests(TestCase):
    def setUp(self):
        self.user = make_user('student')

    def complete_on(self, day):
        task = make_task(
            self.user,
            title=f'Done on {day}',
            status='Completed'
        )

        Task.objects.filter(pk=task.pk).update(
            updated_at=timezone.make_aware(
                datetime.combine(
                    day,
                    time(12, 0)
                )
            )
        )

    def test_no_completed_tasks_means_no_streak(self):
        make_task(self.user, title='Still open')

        self.assertEqual(get_study_streak(self.user), 0)

    def test_a_streak_counts_consecutive_days_up_to_today(self):
        self.complete_on(TODAY)
        self.complete_on(YESTERDAY)
        self.complete_on(YESTERDAY - timedelta(days=1))

        self.assertEqual(get_study_streak(self.user), 3)

    def test_a_gap_breaks_the_streak(self):
        self.complete_on(TODAY)
        self.complete_on(YESTERDAY - timedelta(days=1))

        self.assertEqual(get_study_streak(self.user), 1)

    def test_an_unfinished_today_does_not_break_a_live_streak(self):
        self.complete_on(YESTERDAY)
        self.complete_on(YESTERDAY - timedelta(days=1))

        self.assertEqual(get_study_streak(self.user), 2)

    def test_an_old_streak_reads_as_zero(self):
        self.complete_on(YESTERDAY - timedelta(days=4))

        self.assertEqual(get_study_streak(self.user), 0)

    def test_only_completed_tasks_count(self):
        task = make_task(
            self.user,
            title='Open',
            status='In Progress'
        )

        Task.objects.filter(pk=task.pk).update(
            updated_at=timezone.now()
        )

        self.assertEqual(get_study_streak(self.user), 0)

    def test_another_users_tasks_do_not_count(self):
        other = make_user('other')

        task = make_task(
            other,
            title='Theirs',
            status='Completed'
        )

        Task.objects.filter(pk=task.pk).update(
            updated_at=timezone.now()
        )

        self.assertEqual(get_study_streak(self.user), 0)


class NotificationTests(TestCase):
    def setUp(self):
        self.user = make_user('student')

    def build(self, **counts):
        return get_notifications(
            user=self.user,
            overdue_tasks=counts.get('overdue', 0),
            due_soon_tasks=counts.get('due_soon', 0),
            high_priority_tasks=counts.get('priority', 0),
        )

    def test_nothing_to_report_returns_an_empty_list(self):
        self.assertEqual(self.build(), [])

    def test_titles_come_from_the_counts(self):
        titles = [
            item['title']
            for item in self.build(
                overdue=2,
                due_soon=1,
                priority=3
            )
        ]

        self.assertEqual(
            titles,
            [
                'Overdue',
                'Due soon',
                'High priority',
            ]
        )

    def test_plural_reads_correctly_for_one(self):
        items = self.build(overdue=1)

        self.assertEqual(items[0]['count'], 1)
        self.assertNotIn('s ', items[0]['detail'])

    def test_every_link_points_at_a_real_filtered_task_list(self):
        for item in self.build(
            overdue=1,
            due_soon=1,
            priority=1
        ):

            self.assertTrue(
                item['url'].startswith(reverse('tasks') + '?'),
                msg=item['url'],
            )

    def test_due_soon_links_to_todays_real_due_date_filter(self):
        items = self.build(due_soon=1)

        self.assertIn(
            f'due_date={TODAY.isoformat()}',
            items[0]['url'],
        )


class MonthCalendarTests(TestCase):
    def setUp(self):
        self.user = make_user('student')

    def test_grid_starts_on_a_monday_and_covers_five_or_six_weeks(self):
        grid = get_month_calendar(self.user, today=TODAY)

        first = grid['weeks'][0][0]['date']

        self.assertEqual(first.weekday(), 0)
        self.assertIn(len(grid['weeks']), (5, 6))

    def test_grid_ends_on_a_sunday(self):
        grid = get_month_calendar(self.user, today=TODAY)

        self.assertEqual(
            grid['weeks'][-1][-1]['date'].weekday(),
            6
        )

    def test_every_week_has_seven_days(self):
        grid = get_month_calendar(self.user, today=TODAY)

        for week in grid['weeks']:

            self.assertEqual(len(week), 7)

    def test_days_outside_the_month_are_flagged(self):
        grid = get_month_calendar(self.user, today=TODAY)

        for week in grid['weeks']:
            for day in week:

                self.assertEqual(
                    day['in_month'],
                    day['date'].month == grid['month'],
                )

    def test_today_is_marked(self):
        grid = get_month_calendar(self.user, today=TODAY)

        marked = [
            day
            for week in grid['weeks']
            for day in week
            if day['is_today']
        ]

        self.assertEqual(len(marked), 1)
        self.assertEqual(marked[0]['date'], TODAY)

    def test_open_tasks_appear_as_markers_with_their_priority(self):
        make_task(
            self.user,
            title='Urgent',
            due_date=TODAY,
            priority='High'
        )

        make_task(
            self.user,
            title='Calm',
            due_date=TODAY,
            priority='Low'
        )

        grid = get_month_calendar(self.user, today=TODAY)

        today_cell = next(
            day
            for week in grid['weeks']
            for day in week
            if day['is_today']
        )

        self.assertEqual(today_cell['open_count'], 2)

        # The busiest priority of the day wins the dot colour.
        self.assertEqual(today_cell['tone'], 'high')
        self.assertEqual(grid['open_total'], 2)

    def test_completed_tasks_do_not_count_as_open(self):
        make_task(
            self.user,
            title='Finished',
            due_date=TODAY,
            status='Completed'
        )

        grid = get_month_calendar(self.user, today=TODAY)

        today_cell = next(
            day
            for week in grid['weeks']
            for day in week
            if day['is_today']
        )

        self.assertEqual(today_cell['open_count'], 0)
        self.assertEqual(today_cell['done_count'], 1)
        self.assertIsNone(today_cell['tone'])

    def test_undated_tasks_are_never_marked(self):
        make_task(self.user, title='No due date')

        grid = get_month_calendar(self.user, today=TODAY)

        self.assertEqual(grid['open_total'], 0)

    def test_another_users_tasks_are_never_marked(self):
        make_task(
            make_user('other'),
            title='Theirs',
            due_date=TODAY
        )

        grid = get_month_calendar(self.user, today=TODAY)

        self.assertEqual(grid['open_total'], 0)

    def test_label_matches_the_month(self):
        grid = get_month_calendar(self.user, today=TODAY)

        self.assertEqual(
            grid['label'],
            calendar_module.month_name[grid['month']]
            + f' {grid["year"]}',
        )

    def test_a_month_that_starts_on_sunday_still_begins_on_monday(self):
        grid = get_month_calendar(
            self.user,
            today=date(2026, 2, 1),
            year=2026,
            month=2,
        )

        # 1 February 2026 is a Sunday, so the grid opens on
        # 26 January rather than losing the week.
        self.assertEqual(
            grid['weeks'][0][0]['date'],
            date(2026, 1, 26)
        )


class DashboardSectionTests(TestCase):
    def setUp(self):
        self.user = make_user('student')

    def test_stats_expose_the_new_sections(self):
        stats = get_dashboard_stats(self.user)

        for key in (
            'todays_tasks',
            'subject_progress',
            'streak_days',
            'notifications',
            'calendar',
        ):

            self.assertIn(key, stats)

    def test_todays_tasks_holds_only_todays_dated_tasks(self):
        make_task(self.user, title='For today', due_date=TODAY)
        make_task(self.user, title='For later', due_date=TOMORROW)
        make_task(self.user, title='Undated')

        stats = get_dashboard_stats(self.user)

        self.assertEqual(
            [task.title for task in stats['todays_tasks']],
            ['For today'],
        )

    def test_new_sections_are_scoped_to_the_signed_in_user(self):
        other = make_user('other')

        Subject.objects.create(user=other, name='Theirs')
        make_task(other, title='Theirs', due_date=TODAY)

        stats = get_dashboard_stats(self.user)

        self.assertEqual(stats['subject_progress'], [])
        self.assertEqual(list(stats['todays_tasks']), [])
        self.assertEqual(stats['streak_days'], 0)

    def test_dashboard_renders_the_new_sections(self):
        self.client.force_login(self.user)

        subject = Subject.objects.create(
            user=self.user,
            name='Astronomy'
        )

        make_task(
            self.user,
            subject=subject,
            title='Chart the stars',
            due_date=TODAY
        )

        response = self.client.get(
            reverse('dashboard')
        )

        self.assertContains(response, 'Chart the stars')
        self.assertContains(response, 'Astronomy')
        self.assertContains(response, 'Today\'s Tasks')
        self.assertContains(response, 'Subject Progress')
        self.assertContains(response, 'Quick Actions')
        self.assertContains(response, 'Calendar')

    def test_dashboard_marks_up_a_real_month_grid(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('dashboard')
        )

        self.assertContains(response, 'sb-cal__grid')
        self.assertContains(response, 'sb-cal__day--today')


class TopBarContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = make_user('student')

    def test_anonymous_requests_get_nothing(self):
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get('/')
        request.user = AnonymousUser()

        self.assertEqual(studybuddy_context(request), {})

    def test_signed_in_requests_get_a_streak_and_alerts(self):
        make_task(
            self.user,
            title='Late',
            due_date=YESTERDAY
        )

        request = self.factory.get('/')
        request.user = self.user

        context = studybuddy_context(request)

        self.assertIn('sb_streak', context)
        self.assertEqual(context['sb_alert_count'], 1)
        self.assertEqual(
            [item['title'] for item in context['sb_notifications']],
            ['Overdue'],
        )

    def test_completed_today_does_not_raise_the_alert_badge(self):
        task = make_task(
            self.user,
            title='Finished',
            status='Completed'
        )

        Task.objects.filter(pk=task.pk).update(
            updated_at=timezone.now()
        )

        request = self.factory.get('/')
        request.user = self.user

        context = studybuddy_context(request)

        self.assertEqual(context['sb_alert_count'], 0)
        self.assertEqual(context['sb_streak'], 1)
        self.assertIn(
            'Finished today',
            [
                item['title']
                for item in context['sb_notifications']
            ],
        )

    def test_the_top_bar_appears_on_every_signed_in_page(self):
        self.client.force_login(self.user)

        for url in (
            reverse('dashboard'),
            reverse('subjects'),
            reverse('tasks'),
            reverse('notes'),
        ):

            response = self.client.get(url)

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'sb-search__input')
            self.assertContains(response, 'sb-streak')
