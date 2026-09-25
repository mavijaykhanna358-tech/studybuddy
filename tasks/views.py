import os
import time
import mimetypes
import hashlib
import requests

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import SubjectForm, TaskForm, NoteForm
from .models import Subject, Task, Note


# ============================================================
# CLOUDINARY
# ============================================================

def upload_note_attachment(uploaded_file):

    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key = os.getenv("CLOUDINARY_API_KEY")
    api_secret = os.getenv("CLOUDINARY_API_SECRET")

    if not cloud_name or not api_key or not api_secret:
        raise ValueError(
            "Cloudinary environment variables are not configured."
        )

    if not uploaded_file:
        raise ValueError("No file was selected.")

    max_size = 50 * 1024 * 1024

    if uploaded_file.size > max_size:
        raise ValueError(
            "File is too large. Maximum allowed size is 50 MB."
        )

    original_name = uploaded_file.name or "file"

    extension = os.path.splitext(
        original_name
    )[1].lower()

    content_type = (
        uploaded_file.content_type
        or mimetypes.guess_type(original_name)[0]
        or ""
    ).lower()

    if (
        content_type.startswith("image/")
        or extension == ".pdf"
    ):
        resource_type = "image"
    else:
        resource_type = "raw"

    unique_name = (
        f"note_{int(time.time() * 1000)}"
    )

    if resource_type == "raw":
        public_id = (
            f"{unique_name}{extension}"
        )
    else:
        public_id = unique_name

    timestamp = int(time.time())

    signature_string = (
        f"folder=media/notes"
        f"&public_id={public_id}"
        f"&timestamp={timestamp}"
        f"{api_secret}"
    )

    signature = hashlib.sha1(
        signature_string.encode("utf-8")
    ).hexdigest()

    upload_url = (
        f"https://api.cloudinary.com/v1_1/"
        f"{cloud_name}/{resource_type}/upload"
    )

    uploaded_file.seek(0)

    response = requests.post(
        upload_url,
        data={
            "api_key": api_key,
            "timestamp": timestamp,
            "signature": signature,
            "folder": "media/notes",
            "public_id": public_id,
        },
        files={
            "file": (
                original_name,
                uploaded_file,
                content_type or "application/octet-stream",
            )
        },
        timeout=120,
    )

    try:
        result = response.json()
    except ValueError:
        result = {}

    if response.status_code != 200:

        error_message = (
            result.get("error", {})
            .get(
                "message",
                "Cloudinary upload failed."
            )
        )

        raise ValueError(error_message)

    secure_url = result.get("secure_url")

    if not secure_url:
        raise ValueError(
            "Cloudinary did not return a secure URL."
        )

    return result


# ============================================================
# DOWNLOAD URL
# ============================================================

def create_download_url(url):

    if not url:
        return ""

    if "/upload/" in url:
        return url.replace(
            "/upload/",
            "/upload/fl_attachment/"
        )

    return url


# ============================================================
# DASHBOARD
# ============================================================

@login_required
def dashboard(request):

    user = request.user
    today = timezone.localdate()

    # --------------------------------------------------------
    # COUNTS
    # --------------------------------------------------------

    subjects_count = Subject.objects.filter(
        user=user
    ).count()

    tasks_count = Task.objects.filter(
        user=user
    ).count()

    completed_tasks_count = Task.objects.filter(
        user=user,
        status="Completed"
    ).count()

    pending_tasks_count = Task.objects.filter(
        user=user,
        status="Pending"
    ).count()

    in_progress_tasks_count = Task.objects.filter(
        user=user,
        status="In Progress"
    ).count()

    notes_count = Note.objects.filter(
        user=user
    ).count()

    # --------------------------------------------------------
    # TASK PROGRESS
    # --------------------------------------------------------

    if tasks_count > 0:
        task_progress = round(
            (
                completed_tasks_count
                / tasks_count
            ) * 100
        )
    else:
        task_progress = 0

    # --------------------------------------------------------
    # TODAY'S TASKS
    # --------------------------------------------------------

    todays_tasks = Task.objects.filter(
        user=user,
        due_date=today
    ).exclude(
        status="Completed"
    ).select_related(
        "subject"
    ).order_by(
        "due_date",
        "priority"
    )

    # --------------------------------------------------------
    # UPCOMING TASKS
    # --------------------------------------------------------

    upcoming_tasks = Task.objects.filter(
        user=user,
        due_date__gte=today
    ).exclude(
        status="Completed"
    ).select_related(
        "subject"
    ).order_by(
        "due_date",
        "priority"
    )

    # --------------------------------------------------------
    # RECENT NOTES
    # --------------------------------------------------------

    recent_notes = Note.objects.filter(
        user=user
    ).select_related(
        "subject"
    ).order_by(
        "-updated_at"
    )

    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    context = {
        "subjects_count": subjects_count,
        "tasks_count": tasks_count,
        "completed_tasks_count": completed_tasks_count,
        "pending_tasks_count": pending_tasks_count,
        "in_progress_tasks_count": in_progress_tasks_count,
        "notes_count": notes_count,

        "task_progress": task_progress,

        "todays_tasks": todays_tasks,
        "upcoming_tasks": upcoming_tasks,
        "recent_notes": recent_notes,
    }

    return render(
        request,
        "dashboard/dashboard.html",
        context
    )


# ============================================================
# SUBJECTS
# ============================================================

@login_required
def subject_list(request):

    q = request.GET.get(
        "q",
        ""
    ).strip()

    subjects = Subject.objects.filter(
        user=request.user
    ).order_by("name")

    if q:
        subjects = subjects.filter(
            name__icontains=q
        )

    return render(
        request,
        "subjects/subject_list.html",
        {
            "subjects": subjects,
            "q": q,
        }
    )


@login_required
def subject_create(request):

    if request.method == "POST":

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
                "Subject added successfully."
            )

            return redirect("subjects")

    else:

        form = SubjectForm()

    return render(
        request,
        "subjects/subject_form.html",
        {
            "form": form,
            "title": "Add Subject",
            "button_text": "Add Subject",
        }
    )


@login_required
def subject_detail(request, pk):

    subject = get_object_or_404(
        Subject,
        pk=pk,
        user=request.user
    )

    return render(
        request,
        "subjects/subject_detail.html",
        {
            "subject": subject,
        }
    )


@login_required
def subject_update(request, pk):

    subject = get_object_or_404(
        Subject,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":

        form = SubjectForm(
            request.POST,
            instance=subject
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Subject updated successfully."
            )

            return redirect("subjects")

    else:

        form = SubjectForm(
            instance=subject
        )

    return render(
        request,
        "subjects/subject_form.html",
        {
            "form": form,
            "subject": subject,
            "title": "Edit Subject",
            "button_text": "Save Changes",
        }
    )


@login_required
def subject_delete(request, pk):

    subject = get_object_or_404(
        Subject,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":

        subject.delete()

        messages.success(
            request,
            "Subject deleted successfully."
        )

        return redirect("subjects")

    return render(
        request,
        "subjects/subject_confirm_delete.html",
        {
            "subject": subject,
        }
    )


# ============================================================
# TASKS
# ============================================================

@login_required
def tasks_list(request):

    q = request.GET.get(
        "q",
        ""
    ).strip()

    status = request.GET.get(
        "status",
        ""
    ).strip()

    priority = request.GET.get(
        "priority",
        ""
    ).strip()

    subject_id = request.GET.get(
        "subject",
        ""
    ).strip()

    tasks = Task.objects.filter(
        user=request.user
    ).select_related(
        "subject"
    ).order_by(
        "due_date",
        "priority"
    )

    if q:

        tasks = tasks.filter(
            Q(title__icontains=q)
            |
            Q(description__icontains=q)
        )

    if status:

        tasks = tasks.filter(
            status=status
        )

    if priority:

        tasks = tasks.filter(
            priority=priority
        )

    if subject_id:

        tasks = tasks.filter(
            subject_id=subject_id
        )

    subjects = Subject.objects.filter(
        user=request.user
    ).order_by("name")

    return render(
        request,
        "tasks/task_list.html",
        {
            "tasks": tasks,
            "subjects": subjects,
            "q": q,
            "selected_status": status,
            "selected_priority": priority,
            "selected_subject": subject_id,
        }
    )


@login_required
def task_create(request):

    if request.method == "POST":

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
                "Task added successfully."
            )

            return redirect("tasks")

    else:

        form = TaskForm(
            user=request.user
        )

    return render(
        request,
        "tasks/task_form.html",
        {
            "form": form,
            "title": "Add Task",
            "button_text": "Add Task",
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
        "tasks/task_detail.html",
        {
            "task": task,
        }
    )


@login_required
def task_update(request, pk):

    task = get_object_or_404(
        Task,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":

        form = TaskForm(
            request.POST,
            instance=task,
            user=request.user
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Task updated successfully."
            )

            return redirect("tasks")

    else:

        form = TaskForm(
            instance=task,
            user=request.user
        )

    return render(
        request,
        "tasks/task_form.html",
        {
            "form": form,
            "task": task,
            "title": "Edit Task",
            "button_text": "Save Changes",
        }
    )


@login_required
def task_delete(request, pk):

    task = get_object_or_404(
        Task,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":

        task.delete()

        messages.success(
            request,
            "Task deleted successfully."
        )

        return redirect("tasks")

    return render(
        request,
        "tasks/confirm_delete.html",
        {
            "task": task,
        }
    )


@login_required
def task_complete(request, pk):

    task = get_object_or_404(
        Task,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":

        task.status = "Completed"

        task.save(
            update_fields=["status"]
        )

        messages.success(
            request,
            "Task marked as completed."
        )

    return redirect("tasks")


# ============================================================
# NOTES
# ============================================================

@login_required
def note_list(request):

    q = request.GET.get(
        "q",
        ""
    ).strip()

    subject_id = request.GET.get(
        "subject",
        ""
    ).strip()

    notes = Note.objects.filter(
        user=request.user
    ).select_related(
        "subject"
    ).order_by(
        "-updated_at"
    )

    if q:

        notes = notes.filter(
            Q(title__icontains=q)
            |
            Q(content__icontains=q)
        )

    if subject_id:

        notes = notes.filter(
            subject_id=subject_id
        )

    subjects = Subject.objects.filter(
        user=request.user
    ).order_by("name")

    return render(
        request,
        "notes/note_list.html",
        {
            "notes": notes,
            "subjects": subjects,
            "q": q,
            "selected_subject": subject_id,
        }
    )


@login_required
def note_create(request):

    if request.method == "POST":

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
                "attachment"
            )

            if new_attachment:

                try:

                    upload_result = (
                        upload_note_attachment(
                            new_attachment
                        )
                    )

                    note.attachment.name = (
                        upload_result["public_id"]
                    )

                    note.attachment_url = (
                        upload_result["secure_url"]
                    )

                    note.attachment._committed = True

                except Exception as e:

                    form.add_error(
                        "attachment",
                        f"Upload failed: {e}"
                    )

                    return render(
                        request,
                        "notes/note_form.html",
                        {
                            "form": form,
                            "title": "Add Note",
                            "button_text": "Add Note",
                        }
                    )

            note.save()

            messages.success(
                request,
                "Note added successfully."
            )

            return redirect("notes")

    else:

        form = NoteForm(
            user=request.user
        )

    return render(
        request,
        "notes/note_form.html",
        {
            "form": form,
            "title": "Add Note",
            "button_text": "Add Note",
        }
    )


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
        "notes/note_detail.html",
        {
            "note": note,
            "download_url": download_url,
        }
    )


@login_required
def note_update(request, pk):

    note = get_object_or_404(
        Note,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":

        form = NoteForm(
            request.POST,
            request.FILES,
            instance=note,
            user=request.user
        )

        if form.is_valid():

            note.subject = form.cleaned_data.get(
                "subject"
            )

            note.title = form.cleaned_data.get(
                "title"
            )

            note.content = form.cleaned_data.get(
                "content"
            )

            new_attachment = request.FILES.get(
                "attachment"
            )

            if new_attachment:

                try:

                    upload_result = (
                        upload_note_attachment(
                            new_attachment
                        )
                    )

                    note.attachment.name = (
                        upload_result["public_id"]
                    )

                    note.attachment_url = (
                        upload_result["secure_url"]
                    )

                    note.attachment._committed = True

                except Exception as e:

                    form.add_error(
                        "attachment",
                        f"Upload failed: {e}"
                    )

                    return render(
                        request,
                        "notes/note_form.html",
                        {
                            "form": form,
                            "note": note,
                            "title": "Edit Note",
                            "button_text": "Save Changes",
                        }
                    )

            note.save()

            messages.success(
                request,
                "Note updated successfully."
            )

            return redirect(
                "note_detail",
                pk=note.pk
            )

    else:

        form = NoteForm(
            instance=note,
            user=request.user
        )

    return render(
        request,
        "notes/note_form.html",
        {
            "form": form,
            "note": note,
            "title": "Edit Note",
            "button_text": "Save Changes",
        }
    )


@login_required
def note_delete(request, pk):

    note = get_object_or_404(
        Note,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":

        note.delete()

        messages.success(
            request,
            "Note deleted successfully."
        )

        return redirect("notes")

    return render(
        request,
        "notes/note_confirm_delete.html",
        {
            "note": note,
        }
    )