from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            'tasks',
            '0009_resolve_duplicate_subject_names'
        ),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='task',
            options={'ordering': [models.Case(models.When(due_date__isnull=True, then=1), default=0, output_field=models.IntegerField()), 'due_date', models.Case(models.When(priority='High', then=0), models.When(priority='Medium', then=1), default=2, output_field=models.IntegerField()), 'title']},
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['user', 'status'], name='task_user_status_idx'),
        ),
        migrations.AddIndex(
            model_name='task',
            index=models.Index(fields=['user', 'due_date'], name='task_user_due_idx'),
        ),
        migrations.AddConstraint(
            model_name='subject',
            constraint=models.UniqueConstraint(fields=('user', 'name'), name='unique_subject_name_per_user'),
        ),
    ]
