from datetime import date, timedelta
import mimetypes
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import NoteForm, SubjectForm, TaskForm
from .models import Note, Subject, Task


# =========================================================
# DASHBOARD
# =========================================================

@login_required
def dashboard(request):

    total_subjects = Subject.objects.filter(
        user=request.user
    ).count()

    user_tasks = Task.objects.filter(
        user=request.user
    )

    total_tasks = user_tasks.count()

    completed_tasks = user_tasks.filter(
        status='Completed'
    ).count()

    pending_tasks = user_tasks.filter(
        status='Pending'
    ).count()

    in_progress_tasks = user_tasks.filter(
        status='In Progress'
    ).count()

    if total_tasks > 0:

        completion_percentage = round(
            (completed_tasks / total_tasks) * 100
        )

    else:

        completion_percentage = 0

    overdue_tasks = user_tasks.filter(
        due_date__lt=date.today()
    ).exclude(
        status='Completed'
    ).count()

    upcoming_tasks = user_tasks.filter(
        due_date__gte=date.today()
    ).exclude(
        status='Completed'
    ).select_related(
        'subject'
    ).order_by(
        'due_date'
    )[:5]

    total_notes = Note.objects.filter(
        user=request.user
    ).count()

    recent_notes = Note.objects.filter(
        user=request.user
    ).select_related(
        'subject'
    ).order_by(
        '-updated_at'
    )[:5]

    return render(
        request,
        'dashboard.html',
        {
            'total_subjects': total_subjects,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'pending_tasks': pending_tasks,
            'in_progress_tasks': in_progress_tasks,
            'completion_percentage': completion_percentage,
            'overdue_tasks': overdue_tasks,
            'upcoming_tasks': upcoming_tasks,
            'total_notes': total_notes,
            'recent_notes': recent_notes,
        }
    )


# =========================================================
# SUBJECTS
# =========================================================

@login_required
def subject_list(request):

    queryset = Subject.objects.filter(
        user=request.user
    ).order_by(
        '-updated_at'
    )

    search = request.GET.get(
        'q',
        ''
    ).strip()

    if search:

        queryset = queryset.filter(
            name__icontains=search
        )

    return render(
        request,
        'subjects/subject_list.html',
        {
            'subjects': queryset,
            'q': search
        }
    )


@login_required
def subject_detail(request, pk):

    subject = get_object_or_404(
        Subject,
        pk=pk,
        user=request.user
    )

    tasks = subject.tasks.filter(
        user=request.user
    ).order_by(
        'due_date',
        'priority',
        'title'
    )

    notes = subject.notes.filter(
        user=request.user
    ).order_by(
        '-updated_at'
    )

    return render(
        request,
        'subjects/subject_detail.html',
        {
            'subject': subject,
            'tasks': tasks,
            'notes': notes
        }
    )


@login_required
def subject_create(request):

    if request.method == 'POST':

        form = SubjectForm(
            request.POST
        )

        if form.is_valid():

            subject = form.save(
                commit=False
            )

            subject.user = request.user

            subject.save()

            messages.success(
                request,
                'Subject created successfully.'
            )

            return redirect(
                'subject_detail',
                pk=subject.pk
            )

    else:

        form = SubjectForm()

    return render(
        request,
        'subjects/subject_form.html',
        {
            'form': form,
            'subject': None
        }
    )


@login_required
def subject_update(request, pk):

    subject = get_object_or_404(
        Subject,
        pk=pk,
        user=request.user
    )

    if request.method == 'POST':

        form = SubjectForm(
            request.POST,
            instance=subject
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                'Subject updated successfully.'
            )

            return redirect(
                'subject_detail',
                pk=subject.pk
            )

    else:

        form = SubjectForm(
            instance=subject
        )

    return render(
        request,
        'subjects/subject_form.html',
        {
            'form': form,
            'subject': subject
        }
    )


@login_required
def subject_delete(request, pk):

    subject = get_object_or_404(
        Subject,
        pk=pk,
        user=request.user
    )

    if request.method == 'POST':

        subject.delete()

        messages.success(
            request,
            'Subject deleted successfully.'
        )

        return redirect(
            'subjects'
        )

    return render(
        request,
        'tasks/confirm_delete.html',
        {
            'object': subject,
            'object_type': 'subject',
            'back_url': reverse(
                'subject_detail',
                args=[subject.pk]
            ),
        }
    )


# =========================================================
# TASKS
# =========================================================

@login_required
def tasks_list(request):

    queryset = Task.objects.filter(
        user=request.user
    ).select_related(
        'subject'
    ).order_by(
        'due_date',
        'priority',
        'title'
    )

    search = request.GET.get(
        'q',
        ''
    ).strip()

    if search:

        queryset = queryset.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search)
        )

    subject_id = request.GET.get(
        'subject'
    )

    if subject_id:

        queryset = queryset.filter(
            subject_id=subject_id
        )

    status = request.GET.get(
        'status'
    )

    if status:

        queryset = queryset.filter(
            status=status
        )

    priority = request.GET.get(
        'priority'
    )

    if priority:

        queryset = queryset.filter(
            priority=priority
        )

    due_date = request.GET.get(
        'due_date'
    )

    if due_date:

        queryset = queryset.filter(
            due_date=due_date
        )

    subjects = Subject.objects.filter(
        user=request.user
    ).order_by(
        'name'
    )

    today = date.today()

    tomorrow = today + timedelta(
        days=1
    )

    return render(
        request,
        'tasks/task_list.html',
        {
            'tasks': queryset,
            'subjects': subjects,
            'q': search,
            'subject_id': subject_id,
            'status': status,
            'priority': priority,
            'due_date': due_date,
            'today': today,
            'tomorrow': tomorrow,
        }
    )


@login_required
def task_detail(request, pk):

    task = get_object_or_404(
        Task,
        pk=pk,
        user=request.user
    )

    return render(
        request,
        'tasks/task_detail.html',
        {
            'task': task
        }
    )


@login_required
def task_create(request):

    if request.method == 'POST':

        form = TaskForm(
            request.POST,
            user=request.user
        )

        if form.is_valid():

            task = form.save(
                commit=False
            )

            task.user = request.user

            task.save()

            messages.success(
                request,
                'Task created successfully.'
            )

            return redirect(
                'tasks'
            )

    else:

        form = TaskForm(
            user=request.user
        )

    return render(
        request,
        'tasks/task_form.html',
        {
            'form': form,
            'task': None
        }
    )


@login_required
def task_update(request, pk):

    task = get_object_or_404(
        Task,
        pk=pk,
        user=request.user
    )

    if request.method == 'POST':

        form = TaskForm(
            request.POST,
            instance=task,
            user=request.user
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                'Task updated successfully.'
            )

            return redirect(
                'task_detail',
                pk=task.pk
            )

    else:

        form = TaskForm(
            instance=task,
            user=request.user
        )

    return render(
        request,
        'tasks/task_form.html',
        {
            'form': form,
            'task': task
        }
    )


@login_required
def task_delete(request, pk):

    task = get_object_or_404(
        Task,
        pk=pk,
        user=request.user
    )

    if request.method == 'POST':

        task.delete()

        messages.success(
            request,
            'Task deleted successfully.'
        )

        return redirect(
            'tasks'
        )

    return render(
        request,
        'tasks/confirm_delete.html',
        {
            'object': task,
            'object_type': 'task',
            'back_url': reverse(
                'task_detail',
                args=[task.pk]
            ),
        }
    )


@login_required
def task_complete(request, pk):

    task = get_object_or_404(
        Task,
        pk=pk,
        user=request.user
    )

    task.status = 'Completed'

    task.save()

    messages.success(
        request,
        'Task marked as completed.'
    )

    return redirect(
        'tasks'
    )


# =========================================================
# NOTES
# =========================================================

@login_required
def note_list(request):

    queryset = Note.objects.filter(
        user=request.user
    ).select_related(
        'subject'
    ).order_by(
        '-updated_at'
    )

    search = request.GET.get(
        'q',
        ''
    ).strip()

    if search:

        queryset = queryset.filter(
            Q(title__icontains=search) |
            Q(content__icontains=search)
        )

    subject_id = request.GET.get(
        'subject'
    )

    if subject_id:

        queryset = queryset.filter(
            subject_id=subject_id
        )

    subjects = Subject.objects.filter(
        user=request.user
    ).order_by(
        'name'
    )

    return render(
        request,
        'notes/note_list.html',
        {
            'notes': queryset,
            'subjects': subjects,
            'q': search,
            'subject_id': subject_id,
        }
    )


@login_required
def note_detail(request, pk):

    note = get_object_or_404(
        Note,
        pk=pk,
        user=request.user
    )

    return render(
        request,
        'notes/note_detail.html',
        {
            'note': note
        }
    )


# =========================================================
# NOTE ATTACHMENT DOWNLOAD
# =========================================================

@login_required
def note_attachment_download(request, pk):

    note = get_object_or_404(
        Note,
        pk=pk,
        user=request.user
    )

    if not note.attachment:
        raise Http404(
            'This note has no attachment.'
        )

    try:

        file = note.attachment.open(
            'rb'
        )

    except Exception:

        raise Http404(
            'Attachment could not be opened.'
        )

    filename = os.path.basename(
        note.attachment.name
    )

    content_type, _ = mimetypes.guess_type(
        filename
    )

    response = FileResponse(
        file,
        as_attachment=True,
        filename=filename
    )

    if content_type:

        response['Content-Type'] = (
            content_type
        )

    return response


# =========================================================
# NOTE CREATE
# =========================================================

@login_required
def note_create(request):

    if request.method == 'POST':

        form = NoteForm(
            request.POST,
            request.FILES,
            user=request.user
        )

        if form.is_valid():

            note = form.save(
                commit=False
            )

            note.user = request.user

            note.save()

            messages.success(
                request,
                'Note created successfully.'
            )

            return redirect(
                'notes'
            )

    else:

        form = NoteForm(
            user=request.user
        )

    return render(
        request,
        'notes/note_form.html',
        {
            'form': form,
            'note': None
        }
    )


# =========================================================
# NOTE UPDATE
# =========================================================

@login_required
def note_update(request, pk):

    note = get_object_or_404(
        Note,
        pk=pk,
        user=request.user
    )

    if request.method == 'POST':

        form = NoteForm(
            request.POST,
            request.FILES,
            instance=note,
            user=request.user
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                'Note updated successfully.'
            )

            return redirect(
                'note_detail',
                pk=note.pk
            )

    else:

        form = NoteForm(
            instance=note,
            user=request.user
        )

    return render(
        request,
        'notes/note_form.html',
        {
            'form': form,
            'note': note
        }
    )


# =========================================================
# NOTE DELETE
# =========================================================

@login_required
def note_delete(request, pk):

    note = get_object_or_404(
        Note,
        pk=pk,
        user=request.user
    )

    if request.method == 'POST':

        note.delete()

        messages.success(
            request,
            'Note deleted successfully.'
        )

        return redirect(
            'notes'
        )

    return render(
        request,
        'tasks/confirm_delete.html',
        {
            'object': note,
            'object_type': 'note',
            'back_url': reverse(
                'note_detail',
                args=[note.pk]
            ),
        }
    )