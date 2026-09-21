from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from tasks.models import Note, Subject, Task


@login_required
def dashboard_home(request):
    subjects = Subject.objects.filter(user=request.user)
    tasks = Task.objects.filter(user=request.user)
    notes = Note.objects.filter(user=request.user)
    today = date.today()

    total_subjects = subjects.count()
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status='Completed').count()
    pending_tasks = tasks.filter(status='Pending').count()
    in_progress_tasks = tasks.filter(status='In Progress').count()
    total_notes = notes.count()
    overdue_tasks = tasks.filter(due_date__lt=today, status__in=['Pending', 'In Progress']).count()
    upcoming_tasks = tasks.filter(due_date__gte=today, status__in=['Pending', 'In Progress']).order_by('due_date')[:5]
    recent_notes = notes.order_by('-updated_at')[:5]
    completion_percentage = round((completed_tasks / total_tasks) * 100) if total_tasks else 0

    context = {
        'user': request.user,
        'total_subjects': total_subjects,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'pending_tasks': pending_tasks,
        'in_progress_tasks': in_progress_tasks,
        'total_notes': total_notes,
        'overdue_tasks': overdue_tasks,
        'upcoming_tasks': upcoming_tasks,
        'recent_notes': recent_notes,
        'completion_percentage': completion_percentage,
    }
    return render(request, 'dashboard/dashboard.html', context)
