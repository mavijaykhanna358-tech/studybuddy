from django.db import migrations


def resolve_duplicate_subject_names(apps, schema_editor):

    # A database level unique constraint on (user, name) is added
    # in the next migration. Existing rows that would violate it
    # are renamed first, otherwise the migration aborts and leaves
    # the deploy half finished.
    #
    # Duplicates are renamed rather than deleted so no task or
    # note loses its subject.

    Subject = apps.get_model(
        'tasks',
        'Subject'
    )

    seen = {}

    subjects = (
        Subject.objects
        .order_by('user_id', 'created_at', 'pk')
    )

    for subject in subjects.iterator():

        key = (
            subject.user_id,
            subject.name.lower(),
        )

        if key not in seen:

            seen[key] = subject.name

            continue

        base_name = subject.name

        # "maths" becomes "maths (2)", "maths (3)" and so on
        # until the name is free.

        suffix = 2

        while True:

            candidate = (
                f'{base_name} ({suffix})'
            )

            candidate_key = (
                subject.user_id,
                candidate.lower(),
            )

            if candidate_key not in seen:

                break

            suffix += 1

        subject.name = candidate

        subject.save(
            update_fields=['name']
        )

        seen[candidate_key] = candidate


def noop_reverse(apps, schema_editor):

    # Renamed subjects are not renamed back, which is safe because
    # nothing references a subject by name.
    pass


class Migration(migrations.Migration):

    dependencies = [
        (
            'tasks',
            '0008_alter_task_options_remove_'
            'note_attachment_url_and_more'
        ),
    ]

    operations = [
        migrations.RunPython(
            resolve_duplicate_subject_names,
            noop_reverse,
        ),
    ]
