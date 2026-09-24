from datetime import date, timedelta
import hashlib
import mimetypes
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import NoteForm, SubjectForm, TaskForm
from .models import Note, Subject, Task


# =========================================================
# BASE DIRECTORY
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv(
    BASE_DIR / '.env'
)


# =========================================================
# CLOUDINARY NOTE ATTACHMENT UPLOAD
# =========================================================

def upload_note_attachment(uploaded_file):

    load_dotenv(
        BASE_DIR / '.env',
        override=True
    )

    cloud_name = os.getenv(
        'CLOUDINARY_CLOUD_NAME'
    )

    api_key = os.getenv(
        'CLOUDINARY_API_KEY'
    )

    api_secret = os.getenv(
        'CLOUDINARY_API_SECRET'
    )

    # -----------------------------------------------------
    # CHECK CLOUDINARY SETTINGS
    # -----------------------------------------------------

    if not cloud_name:

        raise ValueError(
            'CLOUDINARY_CLOUD_NAME is missing.'
        )

    if not api_key:

        raise ValueError(
            'CLOUDINARY_API_KEY is missing.'
        )

    if not api_secret:

        raise ValueError(
            'CLOUDINARY_API_SECRET is missing.'
        )

    # -----------------------------------------------------
    # CHECK FILE
    # -----------------------------------------------------

    if uploaded_file is None:

        raise ValueError(
            'No attachment was selected.'
        )

    if uploaded_file.size == 0:

        raise ValueError(
            'The selected file is empty.'
        )

    # Maximum 50 MB

    max_size = 50 * 1024 * 1024

    if uploaded_file.size > max_size:

        raise ValueError(
            'File is too large. '
            'Please upload a file smaller than 50 MB.'
        )

    # -----------------------------------------------------
    # READ FILE
    # -----------------------------------------------------

    uploaded_file.seek(0)

    file_data = uploaded_file.read()

    if not file_data:

        raise ValueError(
            'Django received an empty file.'
        )

    filename = uploaded_file.name

    extension = Path(
        filename
    ).suffix.lower()

    content_type = (
        uploaded_file.content_type
        or mimetypes.guess_type(filename)[0]
        or 'application/octet-stream'
    )

    # -----------------------------------------------------
    # FILE TYPES
    # -----------------------------------------------------

    image_extensions = {
        '.jpg',
        '.jpeg',
        '.png',
        '.gif',
        '.webp',
        '.bmp',
        '.tiff',
        '.svg'
    }

    pdf_extensions = {
        '.pdf'
    }

    # Images and PDFs are uploaded as image resources.
    # Other files are uploaded as raw resources.

    if (
        extension in image_extensions
        or extension in pdf_extensions
    ):

        resource_type = 'image'

    else:

        resource_type = 'raw'

    # -----------------------------------------------------
    # UNIQUE PUBLIC ID
    # -----------------------------------------------------

    unique_name = (
        f'note_{int(time.time() * 1000)}'
    )

    # IMPORTANT:
    # Do NOT put media/notes inside public_id.
    # The folder is already supplied separately.

    if resource_type == 'raw':

        public_id = (
            f'{unique_name}'
            f'{extension}'
        )

    else:

        public_id = unique_name

    # -----------------------------------------------------
    # TIMESTAMP
    # -----------------------------------------------------

    timestamp = int(
        time.time()
    )

    # -----------------------------------------------------
    # SIGNATURE
    # -----------------------------------------------------

    signature_string = (
        f'folder=media/notes'
        f'&public_id={public_id}'
        f'&timestamp={timestamp}'
        f'{api_secret}'
    )

    signature = hashlib.sha1(
        signature_string.encode(
            'utf-8'
        )
    ).hexdigest()

    # -----------------------------------------------------
    # CLOUDINARY UPLOAD URL
    # -----------------------------------------------------

    upload_url = (
        f'https://api.cloudinary.com/v1_1/'
        f'{cloud_name}/'
        f'{resource_type}/upload'
    )

    # -----------------------------------------------------
    # REQUEST DATA
    # -----------------------------------------------------

    data = {

        'api_key':
            api_key,

        'timestamp':
            timestamp,

        'folder':
            'media/notes',

        'public_id':
            public_id,

        'signature':
            signature,
    }

    # -----------------------------------------------------
    # FILE
    # -----------------------------------------------------

    files = {

        'file': (
            filename,
            file_data,
            content_type
        )
    }

    # -----------------------------------------------------
    # UPLOAD TO CLOUDINARY
    # -----------------------------------------------------

    try:

        response = requests.post(
            upload_url,
            data=data,
            files=files,
            timeout=120
        )

    except requests.RequestException as e:

        raise ValueError(
            f'Could not connect to Cloudinary: {e}'
        )

    # -----------------------------------------------------
    # CLOUDINARY ERROR
    # -----------------------------------------------------

    if response.status_code != 200:

        try:

            error_data = response.json()

            error_message = (
                error_data
                .get('error', {})
                .get(
                    'message',
                    'Unknown Cloudinary error'
                )
            )

        except Exception:

            error_message = response.text

        raise ValueError(
            f'Cloudinary upload failed: '
            f'{error_message}'
        )

    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    try:

        result = response.json()

    except Exception:

        raise ValueError(
            'Cloudinary returned an invalid response.'
        )

    # -----------------------------------------------------
    # SECURE URL
    # -----------------------------------------------------

    if not result.get('secure_url'):

        raise ValueError(
            'Cloudinary did not return a secure URL.'
        )

    return result


# =========================================================
# CREATE DOWNLOAD URL
# =========================================================

def create_download_url(url):

    if not url:

        return ''

    # Cloudinary delivery URLs normally contain
    # /upload/ in the URL.
    #
    # Adding fl_attachment makes the browser download
    # the file instead of displaying it.

    if '/upload/' in url:

        return url.replace(
            '/upload/',
            '/upload/fl_attachment/'
        )

    return url


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
# NOTES LIST
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


# =========================================================
# NOTE DETAIL
# =========================================================

@login_required
def note_detail(request, pk):

    note = get_object_or_404(
        Note,
        pk=pk,
        user=request.user
    )

    download_url = create_download_url(
        note.attachment_url
    )

    return render(
        request,
        'notes/note_detail.html',
        {
            'note': note,
            'download_url': download_url,
        }
    )


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

            new_attachment = request.FILES.get(
                'attachment'
            )

            if new_attachment:

                try:

                    upload_result = (
                        upload_note_attachment(
                            new_attachment
                        )
                    )

                except Exception as e:

                    form.add_error(
                        'attachment',
                        str(e)
                    )

                    return render(
                        request,
                        'notes/note_form.html',
                        {
                            'form': form,
                            'note': note
                        }
                    )

                # Save Cloudinary public ID

                note.attachment.name = (
                    upload_result['public_id']
                )

                # Save exact Cloudinary URL

                note.attachment_url = (
                    upload_result['secure_url']
                )

                # Prevent Django storage from
                # uploading the file again.

                note.attachment._committed = True

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

            subject = form.cleaned_data.get(
                'subject'
            )

            title = form.cleaned_data.get(
                'title'
            )

            content = form.cleaned_data.get(
                'content'
            )

            new_attachment = request.FILES.get(
                'attachment'
            )

            # -------------------------------------------------
            # NO NEW ATTACHMENT
            # -------------------------------------------------

            if not new_attachment:

                note.subject = subject

                note.title = title

                note.content = content

                note.save(
                    update_fields=[
                        'subject',
                        'title',
                        'content',
                        'updated_at'
                    ]
                )

            # -------------------------------------------------
            # NEW ATTACHMENT
            # -------------------------------------------------

            else:

                try:

                    upload_result = (
                        upload_note_attachment(
                            new_attachment
                        )
                    )

                except Exception as e:

                    form.add_error(
                        'attachment',
                        str(e)
                    )

                    return render(
                        request,
                        'notes/note_form.html',
                        {
                            'form': form,
                            'note': note
                        }
                    )

                note.subject = subject

                note.title = title

                note.content = content

                # Save Cloudinary public ID

                note.attachment.name = (
                    upload_result['public_id']
                )

                # Save exact Cloudinary URL

                note.attachment_url = (
                    upload_result['secure_url']
                )

                # File has already been uploaded.
                # Prevent Django storage from uploading again.

                note.attachment._committed = True

                note.save(
                    update_fields=[
                        'subject',
                        'title',
                        'content',
                        'attachment',
                        'attachment_url',
                        'updated_at'
                    ]
                )

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