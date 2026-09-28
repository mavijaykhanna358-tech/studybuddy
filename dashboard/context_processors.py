from datetime import date, timedelta

from tasks.models import Task

from .views import get_notifications, get_study_streak


def studybuddy_context(request):

    # Feeds the top bar on every page: the study streak chip and the
    # notification list. Read only and always scoped to the signed in
    # user, so it is safe to attach to every template.

    if not request.user.is_authenticated:

        return {}

    user = request.user

    today = date.today()

    tomorrow = today + timedelta(days=1)

    tasks = Task.objects.filter(
        user=user
    )

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

        'sb_streak': get_study_streak(user),

        'sb_notifications': get_notifications(
            user=user,
            overdue_tasks=overdue_tasks,
            due_soon_tasks=due_soon_tasks,
            high_priority_tasks=high_priority_tasks,
        ),

        # What the bell badge counts: things that still need a
        # decision today. Completed tasks are not included.

        'sb_alert_count': overdue_tasks + due_soon_tasks,
    }
