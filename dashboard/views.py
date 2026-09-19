from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from tasks.models import Task


@login_required
def dashboard_home(request):
    tasks = Task.objects.filter(user=request.user)
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status='Completed').count()
    pending_tasks = tasks.filter(status='Pending').count()
    high_priority = tasks.filter(priority='High').count()
    recent_tasks = tasks.order_by('-created_at')[:5]

    context = {
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'pending_tasks': pending_tasks,
        'high_priority': high_priority,
        'recent_tasks': recent_tasks,
    }
    return render(request, 'dashboard/dashboard.html', context)
