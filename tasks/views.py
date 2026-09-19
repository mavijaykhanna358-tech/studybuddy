from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from .models import Task


@login_required
def tasks_list(request):
    queryset = Task.objects.filter(user=request.user)

    filter_type = request.GET.get('filter', 'all')
    if filter_type == 'today':
        queryset = queryset.filter(due_date=request.GET.get('date')) if request.GET.get('date') else queryset
    elif filter_type == 'upcoming':
        queryset = queryset.filter(status='Pending')
    elif filter_type == 'completed':
        queryset = queryset.filter(status='Completed')
    elif filter_type == 'high-priority':
        queryset = queryset.filter(priority='High')

    context = {'tasks': queryset, 'filter_type': filter_type}
    return render(request, 'tasks/task_list.html', context)


@login_required
def task_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        category = request.POST.get('category', 'General')
        priority = request.POST.get('priority', 'Medium')
        status = request.POST.get('status', 'Pending')
        due_date = request.POST.get('due_date') or None

        if title:
            Task.objects.create(
                user=request.user,
                title=title,
                description=description,
                category=category,
                priority=priority,
                status=status,
                due_date=due_date,
            )
            return redirect('tasks')

    return render(request, 'tasks/task_form.html')


@login_required
def task_update(request, task_id):
    task = Task.objects.get(id=task_id, user=request.user)

    if request.method == 'POST':
        task.title = request.POST.get('title', task.title)
        task.description = request.POST.get('description', task.description)
        task.category = request.POST.get('category', task.category)
        task.priority = request.POST.get('priority', task.priority)
        task.status = request.POST.get('status', task.status)
        task.due_date = request.POST.get('due_date') or None
        task.save()
        return redirect('tasks')

    return render(request, 'tasks/task_form.html', {'task': task})


@login_required
def task_delete(request, task_id):
    task = Task.objects.get(id=task_id, user=request.user)
    task.delete()
    return redirect('tasks')


@login_required
def task_complete(request, task_id):
    task = Task.objects.get(id=task_id, user=request.user)
    task.status = 'Completed'
    task.save()
    return redirect('tasks')
