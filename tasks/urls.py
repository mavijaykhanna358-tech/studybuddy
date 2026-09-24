from django.urls import path

from . import views


urlpatterns = [

    # =====================================================
    # DASHBOARD
    # =====================================================

    path(
        'dashboard/',
        views.dashboard,
        name='dashboard'
    ),


    # =====================================================
    # SUBJECTS
    # =====================================================

    path(
        'subjects/',
        views.subject_list,
        name='subjects'
    ),

    path(
        'subjects/add/',
        views.subject_create,
        name='subject_create'
    ),

    path(
        'subjects/<int:pk>/',
        views.subject_detail,
        name='subject_detail'
    ),

    path(
        'subjects/<int:pk>/edit/',
        views.subject_update,
        name='subject_update'
    ),

    path(
        'subjects/<int:pk>/delete/',
        views.subject_delete,
        name='subject_delete'
    ),


    # =====================================================
    # TASKS
    # =====================================================

    path(
        'tasks/',
        views.tasks_list,
        name='tasks'
    ),

    path(
        'tasks/add/',
        views.task_create,
        name='task_create'
    ),

    path(
        'tasks/<int:pk>/',
        views.task_detail,
        name='task_detail'
    ),

    path(
        'tasks/<int:pk>/edit/',
        views.task_update,
        name='task_edit'
    ),

    path(
        'tasks/<int:pk>/delete/',
        views.task_delete,
        name='task_delete'
    ),

    path(
        'tasks/<int:pk>/complete/',
        views.task_complete,
        name='task_complete'
    ),


    # =====================================================
    # NOTES
    # =====================================================

    path(
        'notes/',
        views.note_list,
        name='notes'
    ),

    path(
        'notes/add/',
        views.note_create,
        name='note_create'
    ),

    path(
        'notes/<int:pk>/',
        views.note_detail,
        name='note_detail'
    ),

    path(
        'notes/<int:pk>/edit/',
        views.note_update,
        name='note_edit'
    ),

    path(
        'notes/<int:pk>/delete/',
        views.note_delete,
        name='note_delete'
    ),

]