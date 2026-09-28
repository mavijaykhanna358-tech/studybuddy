from datetime import date, timedelta
import mimetypes
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, When
from django.http import FileResponse, Http404
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import NoteForm, SubjectForm, TaskForm
from .models import Note, Subject, Task


# =========================================================
# SHARED HELPERS
# =========================================================

def _dated_first():
    # Both SQLite and PostgreSQL sort NULL dates before real ones on
    # an ascending sort, which would float every undated task to
    # the top of the list. This pushes them to the end instead,
    # which is what Task.Meta.ordering documents.

    return Case(
        When(
            due_date__isnull=True,
            then=1
        ),
        default=0,
        output_field=IntegerField(),
    )


def _by_urgency():
    # `priority` is a CharField, so `order_by('priority')` sorts
    # the labels alphabetically and produces High, Low, Medium.
    # These cases order by real urgency instead.

    return Case(
        When(
            priority='High',
            then=0
        ),
        When(
            priority='Medium',
            then=1
        ),
        default=2,
        output_field=IntegerField(),
    )


# Dated tasks first, soonest at the top, most urgent first inside
# each due date, undated tasks at the bottom.

TASK_ORDER = [
    _dated_first(),
    'due_date',
    _by_urgency(),
    'title',
]


# The order behind each `sort=` value in the task list filter.

TASK_SORTS = {
    'due_asc': [
        _dated_first(),
        'due_date',
        'title',
    ],

    'due_desc': [
        _dated_first(),
        '-due_date',
        'title',
    ],

    'priority': [
        _by_urgency(),
        _dated_first(),
        'due_date',
        'title',
    ],

    'title': [
        'title',
    ],

    'newest': [
        '-created_at',
    ],
}


def paginate(request, queryset, per_page=9):

    # Keeps long task and note lists usable instead of rendering
    # every row at once.

    paginator = Paginator(
        queryset,
        per_page
    )

    page_number = request.GET.get('page')

    return paginator.get_page(page_number)


def build_query_string(request, **overrides):

    # Rebuilds the current filter query string for pagination links
    # and for keeping a sort order across pages.

    params = request.GET.copy()

    for key, value in overrides.items():

        if value in (None, ''):

            params.pop(key, None)

        else:

            params[key] = value

    params.pop('page', None)

    return params.urlencode()


def owned_subject_id(request):

    # Reads a `subject` id from the query string and only returns it
    # when the subject actually belongs to the signed in user, so a
    # crafted URL cannot prefill somebody else's subject.

    subject_id = request.GET.get('subject')

    if not subject_id or not subject_id.isdigit():

        return None

    subject_id = int(subject_id)

    if not Subject.objects.filter(
        pk=subject_id,
        user=request.user
    ).exists():

        return None

    return subject_id


# =========================================================
# SUBJECTS
# =========================================================

@login_required
def subject_list(request):

    queryset = Subject.objects.filter(
        user=request.user
    ).annotate(
        # Counts are computed by the database so the template does
        # not trigger two extra queries per subject card.

        task_count=Count(
            'tasks',
            distinct=True
        ),

        note_count=Count(
            'notes',
            distinct=True
        ),
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

    page = paginate(
        request,
        queryset,
        per_page=9
    )

    return render(
        request,
        'subjects/subject_list.html',
        {
            'subjects': page,
            'page_obj': page,
            'query_string': build_query_string(request),
            'q': search,
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
        *TASK_ORDER
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
            request.POST,
            user=request.user
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

        form = SubjectForm(
            user=request.user
        )

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
            instance=subject,
            user=request.user
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
            instance=subject,
            user=request.user
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

    task_count = subject.tasks.count()

    note_count = subject.notes.count()

    return render(
        request,
        'tasks/confirm_delete.html',
        {
            'object': subject,
            'object_name': subject.name,
            'object_type': 'subject',
            'object_type_label': 'subject',
            'task_count': task_count,
            'note_count': note_count,
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
        *TASK_ORDER
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

    # Values from the query string are validated before they reach
    # the ORM, so a hand edited URL cannot produce a broken filter
    # or a database error.

    subject_id = request.GET.get(
        'subject'
    )

    if subject_id:

        if not subject_id.isdigit():

            subject_id = None

        else:

            subject_id = int(subject_id)

            # Only allow filtering by a subject the user owns.

            if not Subject.objects.filter(
                pk=subject_id,
                user=request.user
            ).exists():

                subject_id = None

    if subject_id:

        queryset = queryset.filter(
            subject_id=subject_id
        )

    status = request.GET.get(
        'status'
    )

    if status and status not in dict(Task.STATUS_CHOICES):

        status = None

    if status:

        queryset = queryset.filter(
            status=status
        )

    priority = request.GET.get(
        'priority'
    )

    if priority and priority not in dict(Task.PRIORITY_CHOICES):

        priority = None

    if priority:

        queryset = queryset.filter(
            priority=priority
        )

    due_date = request.GET.get(
        'due_date'
    )

    if due_date:

        try:

            date.fromisoformat(due_date)

        except ValueError:

            due_date = None

    if due_date:

        queryset = queryset.filter(
            due_date=due_date
        )

    sort = request.GET.get(
        'sort',
        ''
    )

    if sort in TASK_SORTS:

        queryset = queryset.order_by(
            *TASK_SORTS[sort]
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

    page = paginate(
        request,
        queryset,
        per_page=9
    )

    return render(
        request,
        'tasks/task_list.html',
        {
            'tasks': page,
            'page_obj': page,
            'query_string': build_query_string(request),
            'subjects': subjects,
            'q': search,
            'subject_id': subject_id,
            'status': status,
            'priority': priority,
            'due_date': due_date,
            'sort': sort,
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

    # The template compares due dates against these, so it can
    # highlight today, tomorrow and overdue without doing any
    # date maths in the template language.

    today = date.today()

    return render(
        request,
        'tasks/task_detail.html',
        {
            'task': task,
            'today': today,
            'tomorrow': today + timedelta(days=1),
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

        # Arriving from a subject page prefills the subject picker.

        initial = {}

        subject_id = owned_subject_id(request)

        if subject_id:

            initial['subject'] = subject_id

        form = TaskForm(
            user=request.user,
            initial=initial
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
            'object_name': task.title,
            'object_type': 'task',
            'object_type_label': 'task',
            'back_url': reverse(
                'task_detail',
                args=[task.pk]
            ),
        }
    )


@login_required
def task_toggle(request, pk):

    # This changes database state, so it only accepts POST.
    # A plain link would let any page or prefetcher mark tasks
    # as completed for the signed in user.

    task = get_object_or_404(
        Task,
        pk=pk,
        user=request.user
    )

    if request.method != 'POST':

        return redirect('task_detail', pk=task.pk)

    if task.status == 'Completed':

        task.status = 'Pending'

        messages.info(
            request,
            'Task marked as pending.'
        )

    else:

        task.status = 'Completed'

        messages.success(
            request,
            'Task marked as completed.'
        )

    task.save(
        update_fields=[
            'status',
            'updated_at',
            'reminder_sent_at',
        ]
    )

    # Return the user to wherever the action was triggered from,
    # but only to a path inside this app.

    next_url = request.POST.get('next') or request.META.get(
        'HTTP_REFERER'
    )

    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={
            request.get_host(),
        },
        require_https=request.is_secure(),
    ):

        return HttpResponseRedirect(next_url)

    return redirect('tasks')


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

        if not subject_id.isdigit():

            subject_id = None

        else:

            subject_id = int(subject_id)

            if not Subject.objects.filter(
                pk=subject_id,
                user=request.user
            ).exists():

                subject_id = None

    if subject_id:

        queryset = queryset.filter(
            subject_id=subject_id
        )

    subjects = Subject.objects.filter(
        user=request.user
    ).order_by(
        'name'
    )

    page = paginate(
        request,
        queryset,
        per_page=9
    )

    return render(
        request,
        'notes/note_list.html',
        {
            'notes': page,
            'page_obj': page,
            'query_string': build_query_string(request),
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

    except Exception as error:

        raise Http404(
            'Attachment could not be opened.'
        ) from error

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

        initial = {}

        subject_id = owned_subject_id(request)

        if subject_id:

            initial['subject'] = subject_id

        form = NoteForm(
            user=request.user,
            initial=initial
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
            'object_name': note.title,
            'object_type': 'note',
            'object_type_label': 'note',
            'back_url': reverse(
                'note_detail',
                args=[note.pk]
            ),
        }
    )


# =========================================================
# GLOBAL SEARCH
# =========================================================

@login_required
def search(request):

    # Read only view that backs the search box in the top bar. It
    # searches the signed in user's own subjects, tasks and notes
    # and never exposes anybody else's rows.

    query = request.GET.get(
        'q',
        ''
    ).strip()

    results = {
        'subjects': Subject.objects.none(),
        'tasks': Task.objects.none(),
        'notes': Note.objects.none(),
    }

    total = 0

    if query:

        results['subjects'] = Subject.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query),
            user=request.user,
        ).order_by(
            'name'
        )[:5]

        results['tasks'] = Task.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query),
            user=request.user,
        ).select_related(
            'subject'
        ).order_by(
            'due_date',
            'title'
        )[:5]

        results['notes'] = Note.objects.filter(
            Q(title__icontains=query) |
            Q(content__icontains=query),
            user=request.user,
        ).select_related(
            'subject'
        ).order_by(
            '-updated_at'
        )[:5]

        total = (
            results['subjects'].count() +
            results['tasks'].count() +
            results['notes'].count()
        )

    return render(
        request,
        'tasks/search.html',
        {
            'q': query,
            'results': results,
            'total': total,
        }
    )