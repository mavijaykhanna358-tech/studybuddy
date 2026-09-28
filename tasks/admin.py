from django.contrib import admin
from django.db.models import Count

from .models import Note, Subject, Task


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):

    list_display = [
        'name',
        'user',
        'task_total',
        'note_total',
        'updated_at',
    ]

    list_filter = [
        'created_at',
    ]

    search_fields = [
        'name',
        'user__username',
    ]

    ordering = [
        '-updated_at',
    ]

    autocomplete_fields = [
        'user',
    ]

    def get_queryset(self, request):
        # Count comes from django.db.models. It was reached here as
        # admin.models.Count, which django.contrib.admin.models has
        # never exported, so this raised AttributeError as soon as
        # the queryset was built and every request for this
        # changelist returned a 500.

        return super().get_queryset(
            request
        ).annotate(
            task_total=Count('tasks'),
            note_total=Count('notes'),
        )

    @admin.display(
        description='Tasks',
        ordering='task_total',
    )
    def task_total(self, obj):
        return obj.task_total

    @admin.display(
        description='Notes',
        ordering='note_total',
    )
    def note_total(self, obj):
        return obj.note_total


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):

    list_display = [
        'title',
        'user',
        'subject',
        'status',
        'priority',
        'due_date',
    ]

    list_filter = [
        'status',
        'priority',
        'due_date',
    ]

    search_fields = [
        'title',
        'description',
        'user__username',
    ]

    list_select_related = [
        'user',
        'subject',
    ]

    date_hierarchy = 'due_date'

    ordering = [
        'due_date',
    ]

    autocomplete_fields = [
        'user',
        'subject',
    ]


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):

    list_display = [
        'title',
        'user',
        'subject',
        'has_attachment',
        'updated_at',
    ]

    list_filter = [
        'updated_at',
    ]

    search_fields = [
        'title',
        'content',
        'user__username',
    ]

    list_select_related = [
        'user',
        'subject',
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
    ]

    ordering = [
        '-updated_at',
    ]

    autocomplete_fields = [
        'user',
        'subject',
    ]

    @admin.display(
        boolean=True,
        description='Attachment',
    )
    def has_attachment(self, obj):
        return bool(obj.attachment)
