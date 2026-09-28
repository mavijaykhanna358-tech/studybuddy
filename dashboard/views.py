import calendar as calendar_module

from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import reverse

from tasks.models import Note, Subject, Task


# =========================================================
# DASHBOARD
# =========================================================

@login_required
def dashboard_home(request):

    stats = get_dashboard_stats(request.user)

    return render(
        request,
        'dashboard/dashboard.html',
        stats
    )


# =========================================================
# STATS
# =========================================================

def get_dashboard_stats(user):

    # Single place that computes the numbers shown on the
    # dashboard. Kept separate from the view so the calculation
    # can be tested without rendering a template.

    today = date.today()

    tomorrow = today + timedelta(days=1)

    tasks = Task.objects.filter(
        user=user
    )

    total_tasks = tasks.count()

    completed_tasks = tasks.filter(
        status='Completed'
    ).count()

    pending_tasks = tasks.filter(
        status='Pending'
    ).count()

    in_progress_tasks = tasks.filter(
        status='In Progress'
    ).count()

    if total_tasks:

        completion_percentage = round(
            (completed_tasks / total_tasks) * 100
        )

    else:

        completion_percentage = 0

    overdue_tasks = tasks.filter(
        due_date__lt=today
    ).exclude(
        status='Completed'
    ).count()

    due_soon_tasks = tasks.filter(
        due_date__in=[
            today,
            tomorrow,
        ]
    ).exclude(
        status='Completed'
    ).count()

    high_priority_tasks = tasks.filter(
        priority='High'
    ).exclude(
        status='Completed'
    ).count()

    return {

        'today': today,
        'tomorrow': tomorrow,

        # Counts

        'total_subjects': Subject.objects.filter(
            user=user
        ).count(),

        'total_tasks': total_tasks,

        'completed_tasks': completed_tasks,

        'pending_tasks': pending_tasks,

        'in_progress_tasks': in_progress_tasks,

        'total_notes': Note.objects.filter(
            user=user
        ).count(),

        # Progress

        'completion_percentage': completion_percentage,

        # Health

        'overdue_tasks': overdue_tasks,

        'due_soon_tasks': due_soon_tasks,

        'high_priority_tasks': high_priority_tasks,

        # Lists

        'upcoming_tasks': tasks.filter(
            due_date__gte=today
        ).exclude(
            status='Completed'
        ).select_related(
            'subject'
        ).order_by(
            'due_date'
        )[:5],

        'recent_notes': Note.objects.filter(
            user=user
        ).select_related(
            'subject'
        ).order_by(
            '-updated_at'
        )[:5],

        # New dashboard sections. Every value below is derived
        # from real rows, nothing is invented.

        'todays_tasks': tasks.filter(
            due_date=today
        ).select_related(
            'subject'
        ).order_by(
            '-priority',
            'title'
        ),

        'subject_progress': get_subject_progress(user),

        'streak_days': get_study_streak(user),

        'notifications': get_notifications(
            user=user,
            overdue_tasks=overdue_tasks,
            due_soon_tasks=due_soon_tasks,
            high_priority_tasks=high_priority_tasks,
        ),

        'calendar': get_month_calendar(user, today),
    }


def get_subject_progress(user):

    # Progress per subject, calculated from that subject's real
    # tasks. Subjects without tasks are kept so the panel can show
    # an honest "no tasks yet" row instead of silently vanishing.

    rows = Subject.objects.filter(
        user=user
    ).annotate(
        total=Count(
            'tasks',
            distinct=True
        ),

        done=Count(
            'tasks',
            filter=Q(
                tasks__status='Completed'
            ),
            distinct=True
        ),
    ).order_by(
        'name'
    )

    progress = []

    for subject in rows:

        percentage = 0

        if subject.total:

            percentage = round(
                (subject.done / subject.total) * 100
            )

        progress.append({

            'subject': subject,
            'total': subject.total,
            'done': subject.done,
            'left': subject.total - subject.done,
            'percentage': percentage,
        })

    return progress


def get_study_streak(user):

    # Consecutive days, counting back from today, on which the user
    # completed at least one task. Task has no "completed at" field,
    # so the last time a completed task was saved is used as the
    # completion timestamp.

    completed_days = set(
        Task.objects.filter(
            user=user,
            status='Completed'
        ).values_list(
            'updated_at',
            flat=True
        )
    )

    days = {
        stamp.date()
        for stamp in completed_days
    }

    if not days:

        return 0

    today = date.today()

    # An unfinished today must not break a streak that is still
    # alive, so counting is allowed to start from yesterday.

    if today in days:

        cursor = today

    elif today - timedelta(days=1) in days:

        cursor = today - timedelta(days=1)

    else:

        return 0

    streak = 0

    while cursor in days:

        streak += 1
        cursor -= timedelta(days=1)

    return streak


def get_notifications(
    user,
    overdue_tasks,
    due_soon_tasks,
    high_priority_tasks,
):

    # Every notification is a real count of real rows, and every link
    # points at the existing task list using a filter that view
    # already supports, so there are no dead links.

    today = date.today()

    notifications = []

    if overdue_tasks:

        notifications.append({

            'tone': 'danger',
            'count': overdue_tasks,
            'title': 'Overdue',
            'detail': 'task{plural} past the due date'.format(
                plural='s' if overdue_tasks != 1 else ''
            ),
            'action': 'Review',
            'url': '{}?sort=due_asc'.format(
                reverse('tasks')
            ),
        })

    if due_soon_tasks:

        notifications.append({

            'tone': 'gold',
            'count': due_soon_tasks,
            'title': 'Due soon',
            'detail': 'task{plural} due today or tomorrow'.format(
                plural='s' if due_soon_tasks != 1 else ''
            ),
            'action': 'Open',
            'url': '{}?due_date={}'.format(
                reverse('tasks'),
                today.isoformat(),
            ),
        })

    if high_priority_tasks:

        notifications.append({

            'tone': 'burgundy',
            'count': high_priority_tasks,
            'title': 'High priority',
            'detail': 'task{plural} still open'.format(
                plural='s' if high_priority_tasks != 1 else ''
            ),
            'action': 'Focus',
            'url': '{}?priority=High&status=Pending'.format(
                reverse('tasks')
            ),
        })

    completed_today = Task.objects.filter(
        user=user,
        status='Completed',
        updated_at__date=today,
    ).count()

    if completed_today:

        notifications.append({

            'tone': 'emerald',
            'count': completed_today,
            'title': 'Finished today',
            'detail': 'task{plural} completed'.format(
                plural='s' if completed_today != 1 else ''
            ),
            'action': 'Review',
            'url': '{}?status=Completed'.format(
                reverse('tasks')
            ),
        })

    return notifications


def get_month_calendar(user, today=None, year=None, month=None):

    # A real month grid. No events are invented: the dots come from
    # tasks that actually have a due date inside the month.

    if today is None:

        today = date.today()

    if year is None or month is None:

        year = today.year
        month = today.month

    first_weekday, days_in_month = calendar_module.monthrange(
        year,
        month
    )

    # Monday first calendar grid. `monthrange` already numbers
    # Monday as 0 and Sunday as 6, which is the order the grid
    # renders in, so no extra shift is needed.

    grid_start = date(year, month, 1) - timedelta(
        days=first_weekday
    )

    last_day = date(year, month, days_in_month)

    grid_end = last_day + timedelta(
        days=6 - last_day.weekday()
    )

    open_by_day = {}
    done_by_day = {}

    ranks = {
        'High': 0,
        'Medium': 1,
        'Low': 2,
    }

    for task in Task.objects.filter(
        user=user,
        due_date__gte=grid_start,
        due_date__lte=grid_end,
    ).values_list(
        'due_date',
        'priority',
        'status',
    ):

        if task[2] == 'Completed':

            done_by_day[task[0]] = done_by_day.get(
                task[0],
                0
            ) + 1

            continue

        entry = open_by_day.setdefault(
            task[0],
            {
                'count': 0,
                'rank': 9,
            }
        )

        entry['count'] += 1

        rank = ranks.get(task[1], 2)

        if rank < entry['rank']:

            entry['rank'] = rank

    tones = {
        0: 'high',
        1: 'medium',
        2: 'low',
    }

    weeks = []
    cursor = grid_start

    while cursor <= grid_end:

        week = []

        for _ in range(7):

            entry = open_by_day.get(cursor)
            done = done_by_day.get(cursor, 0)

            week.append({

                'date': cursor,
                'day': cursor.day,
                'in_month': cursor.month == month,
                'is_today': cursor == today,
                'is_weekend': cursor.weekday() >= 5,
                'open_count': entry['count'] if entry else 0,
                'done_count': done,
                'tone': tones.get(
                    entry['rank']
                ) if entry else None,
            })

            cursor += timedelta(days=1)

        weeks.append(week)

    return {

        'year': year,
        'month': month,
        'label': date(year, month, 1).strftime(
            '%B %Y'
        ),
        'weeks': weeks,
        'open_total': sum(
            entry['count']
            for entry in open_by_day.values()
        ),
    }
