from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from tasks.models import Note, Subject, Task


@login_required
def dashboard_home(request):

    # =========================
    # Subjects
    # =========================

    subjects = Subject.objects.filter(
        user=request.user
    )


    # =========================
    # Tasks
    # =========================

    tasks = Task.objects.filter(
        user=request.user
    )


    # =========================
    # Notes
    # =========================

    notes = Note.objects.filter(
        user=request.user
    )


    today = date.today()


    # =========================
    # Statistics
    # =========================

    total_subjects = subjects.count()

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

    total_notes = notes.count()


    # =========================
    # Overdue Tasks
    # =========================

    overdue_tasks = tasks.filter(
        due_date__lt=today,
        status__in=[
            'Pending',
            'In Progress'
        ]
    ).count()


    # =========================
    # Upcoming Tasks
    # =========================

    upcoming_tasks = tasks.filter(
        due_date__gte=today,
        status__in=[
            'Pending',
            'In Progress'
        ]
    ).select_related(
        'subject'
    ).order_by(
        'due_date'
    )[:5]


    # =========================
    # Recent Notes
    # =========================

    recent_notes = notes.select_related(
        'subject'
    ).order_by(
        '-updated_at'
    )[:5]


    # =========================
    # Task Completion
    # =========================

    if total_tasks:

        completion_percentage = round(
            (completed_tasks / total_tasks) * 100
        )

    else:

        completion_percentage = 0


    # =========================
    # Dashboard Context
    # =========================

    context = {

        'user': request.user,

        # Statistics
        'total_subjects': total_subjects,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'pending_tasks': pending_tasks,
        'in_progress_tasks': in_progress_tasks,

        # Notes
        'total_notes': total_notes,
        'recent_notes': recent_notes,

        # Tasks
        'overdue_tasks': overdue_tasks,
        'upcoming_tasks': upcoming_tasks,
        'completion_percentage': completion_percentage,
    }


    return render(
        request,
        'dashboard/dashboard.html',
        context
    )