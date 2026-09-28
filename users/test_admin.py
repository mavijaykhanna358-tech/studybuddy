"""
Tests for the admin site.

Two admin pages used to return a 500 for reasons that had nothing to
do with each other:

* `CustomUserAdmin.list_select_related` named `date_joined`, a plain
  column rather than a relation, so the Users changelist died with
  `FieldError: Non-relational field given in select_related`.
* `SubjectAdmin.get_queryset` called `admin.models.Count`, which
  django.contrib.admin.models has never exported, so the Subjects
  changelist died with `AttributeError`.

Neither was caught, because the only admin test loaded `/admin/`,
and the index never builds a changelist query. The tests below
therefore load the changelist of every registered model, not just
the index, and additionally resolve every name an admin option
uses, because such a name is only validated when its page is built,
long after the commit that introduced it.
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from tasks.models import Note, Subject, Task


# Options whose entries are names resolved against the model, so a
# field that no longer exists is only reported when the page that
# uses it is opened.

NAME_OPTIONS = (
    'list_display',
    'list_display_links',
    'list_filter',
    'search_fields',
    'readonly_fields',
    'autocomplete_fields',
)


def registered_models():

    return sorted(
        admin.site._registry,
        key=lambda model: model._meta.label_lower,
    )


def names_in(option, value):
    """
    Flatten an admin option into the field names it mentions.

    `fields` and `fieldsets` are the only nested ones. A fieldset is
    either a bare list of names or a (name, {'fields': [...]}) pair,
    and the second element of the pair is a dict, not a field.
    """

    if option == 'fields':

        return list(value)

    if option == 'fieldsets':

        collected = []

        for entry in value:

            if isinstance(entry, (list, tuple)) and entry:

                first = entry[0]

                if isinstance(first, str):

                    collected.append(first)
                    continue

                collected.extend(
                    entry[1].get('fields', ())
                )

        return collected

    return list(value)


class AdminSiteTests(TestCase):
    """The pages an administrator actually opens."""

    def setUp(self):

        self.user = get_user_model().objects.create_superuser(
            username='siteadmin',
            email='admin@studybuddy.example',
            password='Admin-Passphrase-5531',
        )

        self.client.force_login(self.user)

    def test_the_index_loads(self):

        response = self.client.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 200)

    def test_the_users_changelist_loads(self):
        """The page that was returning a 500."""

        response = self.client.get(
            reverse('admin:auth_user_changelist')
        )

        self.assertEqual(response.status_code, 200)

    def test_the_users_changelist_lists_the_accounts(self):

        get_user_model().objects.create_user(
            username='astudent',
            email='astudent@example.com',
            password='Student-Passphrase-7781',
        )

        response = self.client.get(
            reverse('admin:auth_user_changelist')
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'astudent')

    def test_every_registered_changelist_loads(self):
        """The regression guard.

        A broken option made one page a 500 while the rest of the
        site looked healthy. Iterating the registry means a broken
        option on any model fails here instead.
        """

        for model in registered_models():

            with self.subTest(model=model._meta.label_lower):

                response = self.client.get(
                    reverse(
                        f'admin:{model._meta.app_label}'
                        f'_{model._meta.model_name}'
                        f'_changelist'
                    )
                )

                self.assertEqual(response.status_code, 200)

    def test_the_subjects_changelist_loads(self):
        """The second 500, from the annotation import."""

        Subject.objects.create(
            user=self.user,
            name='Mathematics',
        )

        response = self.client.get(
            reverse('admin:tasks_subject_changelist')
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'Mathematics')

    def test_the_subjects_changelist_shows_the_annotations(self):
        """The columns that the broken Count produced."""

        subject = Subject.objects.create(
            user=self.user,
            name='Mathematics',
        )

        Task.objects.create(
            user=self.user,
            subject=subject,
            title='Quadratics',
        )

        Note.objects.create(
            user=self.user,
            subject=subject,
            title='Revision notes',
        )

        response = self.client.get(
            reverse('admin:tasks_subject_changelist')
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'Mathematics')

        changelist = admin.site._registry[Subject].get_changelist_instance(
            self._request()
        )

        row = changelist.queryset.get(name='Mathematics')

        self.assertEqual(row.task_total, 1)
        self.assertEqual(row.note_total, 1)

    def test_searching_the_users_changelist_works(self):
        """A search exercises search_fields, which a plain list does not."""

        get_user_model().objects.create_user(
            username='astudent',
            email='astudent@example.com',
            password='Student-Passphrase-7781',
        )

        response = self.client.get(
            reverse('admin:auth_user_changelist'),
            {'q': 'astudent'},
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'astudent')

        # The signed-in administrator's own name is in the page
        # chrome, so the row count is what proves the search
        # filtered rather than listing everyone.

        self.assertEqual(
            response.context['cl'].result_count,
            1,
        )

    def test_a_search_matching_nobody_returns_no_rows(self):

        get_user_model().objects.create_user(
            username='astudent',
            email='astudent@example.com',
            password='Student-Passphrase-7781',
        )

        response = self.client.get(
            reverse('admin:auth_user_changelist'),
            {'q': 'no-such-account-anywhere'},
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.context['cl'].result_count,
            0,
        )

    def test_the_user_autocomplete_endpoint_works(self):
        """TaskAdmin and SubjectAdmin depend on this to pick an owner.

        A broken user admin breaks task and subject editing too, and
        the failure surfaces as a 500 in the middle of a form rather
        than on the Users page.

        The view is addressed by the model that *declares* the field,
        not the one being looked up, so this asks for tasks/task/user
        and exercises the user admin's search_fields. Asking for
        auth/user instead is a 403, because a primary key has no
        remote_field to follow.
        """

        response = self.client.get(
            reverse('admin:autocomplete'),
            {
                'app_label': 'tasks',
                'model_name': 'task',
                'field_name': 'user',
                'term': 'site',
            },
        )

        self.assertEqual(response.status_code, 200)

        results = response.json()['results']

        self.assertEqual(
            results[0]['id'],
            str(self.user.pk),
        )

    def test_the_subject_autocomplete_endpoint_works(self):

        response = self.client.get(
            reverse('admin:autocomplete'),
            {
                'app_label': 'tasks',
                'model_name': 'subject',
                'field_name': 'user',
                'term': 'site',
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.json()['results'][0]['id'],
            str(self.user.pk),
        )

    def test_the_user_change_page_loads(self):

        response = self.client.get(
            reverse(
                'admin:auth_user_change',
                args=[self.user.pk],
            )
        )

        self.assertEqual(response.status_code, 200)

    def test_the_task_change_page_loads(self):
        """It renders the user autocomplete widget."""

        task = Task.objects.create(
            user=self.user,
            title='Quadratics',
        )

        response = self.client.get(
            reverse(
                'admin:tasks_task_change',
                args=[task.pk],
            )
        )

        self.assertEqual(response.status_code, 200)

    def test_ordinary_accounts_are_still_locked_out(self):
        """The fixes must not have changed who can reach the admin."""

        get_user_model().objects.create_user(
            username='astudent',
            email='astudent@example.com',
            password='Student-Passphrase-7781',
        )

        self.client.logout()

        self.assertTrue(
            self.client.login(
                username='astudent',
                password='Student-Passphrase-7781',
            )
        )

        response = self.client.get(
            reverse('admin:auth_user_changelist')
        )

        self.assertEqual(response.status_code, 302)

    def _request(self):

        request = RequestFactory().get('/admin/')

        request.user = self.user

        return request


class AdminOptionTests(TestCase):
    """Static checks, so a bad name cannot reach a deploy."""

    def test_the_models_expected_are_registered(self):

        labels = {
            model._meta.label_lower
            for model in registered_models()
        }

        for expected in (
            'auth.user',
            'tasks.task',
            'tasks.subject',
            'tasks.note',
        ):

            with self.subTest(model=expected):

                self.assertIn(expected, labels)

    def test_every_named_option_resolves(self):
        """list_display, search_fields and friends are names, not paths.

        A name may be a field, a relation, a lookup across
        relations such as 'user__username', or a method on the
        ModelAdmin such as 'has_attachment'. All four are valid; a
        fifth thing is the bug.
        """

        for model in registered_models():

            model_admin = admin.site._registry[model]

            for option in NAME_OPTIONS:

                value = getattr(model_admin, option, None)

                if not value:
                    continue

                for name in value:

                    if not isinstance(name, str):
                        continue

                    with self.subTest(
                        model=model._meta.label_lower,
                        option=option,
                        name=name,
                    ):

                        self.assertIsNotNone(
                            self.resolve(model, model_admin, name),
                            msg=(
                                f'{model.__name__}.{option} names '
                                f'"{name}", which is not a field, a '
                                f'relation, a lookup or a method'
                            ),
                        )

    def test_fields_and_fieldsets_resolve(self):

        for model in registered_models():

            model_admin = admin.site._registry[model]

            for option in ('fields', 'fieldsets'):

                value = getattr(model_admin, option, None)

                if not value:
                    continue

                for name in names_in(option, value):

                    with self.subTest(
                        model=model._meta.label_lower,
                        option=option,
                        name=name,
                    ):

                        self.assertIsNotNone(
                            self.resolve(
                                model,
                                model_admin,
                                name,
                            )
                        )

    def test_list_select_related_only_names_relations(self):
        """The specific mistake that caused the Users 500.

        select_related joins, so it can only be given a ForeignKey or
        OneToOne. A plain column is accepted when the option is read
        and only fails much later, when the SQL is compiled, which is
        why the page 500s while the admin index still renders.
        """

        checked = []

        for model in registered_models():

            model_admin = admin.site._registry[model]

            names = model_admin.list_select_related

            if not names:
                continue

            for name in names:

                checked.append(name)

                with self.subTest(
                    model=model._meta.label_lower,
                    name=name,
                ):

                    field = model._meta.get_field(name)

                    self.assertTrue(
                        field.is_relation
                        and (
                            field.many_to_one
                            or field.one_to_one
                        ),
                        msg=(
                            f'{model.__name__}'
                            f'.list_select_related names '
                            f'"{name}", which is a '
                            f'{field.__class__.__name__} rather '
                            'than a relation. Django raises '
                            'FieldError: Non-relational field '
                            'given in select_related only when the '
                            'changelist query is compiled, so the '
                            'page 500s while the admin index still '
                            'renders.'
                        ),
                    )

        # The fix was to remove it, so nothing should be left on the
        # user admin to regress.

        self.assertNotIn('date_joined', checked)

    def test_ordering_resolves(self):

        for model in registered_models():

            model_admin = admin.site._registry[model]

            if not model_admin.ordering:

                continue

            for entry in model_admin.ordering:

                if entry in ('?', 'pk', 'id'):

                    continue

                with self.subTest(
                    model=model._meta.label_lower,
                    ordering=entry,
                ):

                    self.assertIsNotNone(
                        self.resolve(
                            model,
                            model_admin,
                            entry,
                            strip_prefix=True,
                        ),
                    )

    def test_date_hierarchy_resolves(self):

        for model in registered_models():

            model_admin = admin.site._registry[model]

            if not getattr(
                model_admin, 'date_hierarchy', None
            ):

                continue

            with self.subTest(
                model=model._meta.label_lower,
            ):

                self.assertIsNotNone(
                    self.resolve(
                        model,
                        model_admin,
                        model_admin.date_hierarchy,
                    )
                )

    def test_every_changelist_queryset_compiles(self):
        """The failure is deferred to SQL compilation.

        Building the ChangeList is not enough, because the error
        surfaces when the queryset is evaluated, so these are
        actually evaluated against the test database.
        """

        request = RequestFactory().get('/admin/')

        request.user = get_user_model().objects.create_superuser(
            username='compileadmin',
            email='compile.admin@example.com',
            password='Compile-Passphrase-9943',
        )

        for model in registered_models():

            model_admin = admin.site._registry[model]

            with self.subTest(model=model._meta.label_lower):

                changelist = model_admin.get_changelist_instance(
                    request
                )

                list(changelist.queryset)

    def test_annotations_named_by_list_display_are_present(self):
        """A list_display column backed by an annotation must exist.

        This is the other half of the SubjectAdmin failure: the import
        was wrong, so the annotation was never applied.
        """

        request = RequestFactory().get('/admin/')

        request.user = get_user_model().objects.create_superuser(
            username='annotateadmin',
            email='annotate.admin@example.com',
            password='Annotate-Passphrase-3307',
        )

        Subject.objects.create(
            user=request.user,
            name='Mathematics',
        )

        model_admin = admin.site._registry[Subject]

        rows = list(
            model_admin.get_changelist_instance(
                request
            ).queryset
        )

        self.assertEqual(len(rows), 1)

        for name in ('task_total', 'note_total'):

            with self.subTest(annotation=name):

                for row in rows:

                    self.assertIsNotNone(
                        getattr(row, name, None)
                    )

    def resolve(self, model, model_admin, name, strip_prefix=False):
        """
        Resolve an admin option entry to a field, relation, lookup or
        method, or None if it is none of those.
        """

        candidate = name

        if strip_prefix:

            candidate = candidate.lstrip('-')

        if hasattr(model, candidate):
            return candidate

        if hasattr(model_admin, candidate):
            return candidate

        try:

            return model._meta.get_field(candidate)

        except Exception:

            pass

        # A lookup path such as 'user__username', or a date lookup
        # such as 'date_joined__year'. Each segment has to exist for
        # the lookup to be valid.

        segments = candidate.split('__')

        if len(segments) > 1:

            current = model

            for segment in segments:

                if segment in ('year', 'month', 'day', 'gt',
                               'gte', 'lt', 'lte', 'exact',
                               'iexact', 'icontains',
                               'contains', 'startswith',
                               'endswith', 'range', 'in',
                               'isnull'):

                    continue

                try:

                    field = current._meta.get_field(segment)

                except Exception:

                    return None

                if field.is_relation:
                    current = field.related_model

            return candidate

        return None


class SchemaTests(TestCase):
    """
    Ruling out the schema as the cause.

    The 500 was a FieldError raised while compiling SQL, before any
    query was sent, so no column was ever missing. These assert the
    columns the admin renders are part of the shipped auth
    migration, which is what the production PostgreSQL schema was
    built from.
    """

    def test_the_user_columns_the_admin_shows_are_auth_columns(self):

        for field in (
            'username',
            'email',
            'is_staff',
            'date_joined',
        ):

            with self.subTest(field=field):

                self.assertIsNotNone(
                    get_user_model()._meta.get_field(field)
                )

    def test_the_auth_migration_defines_date_joined(self):
        """Read the column out of the migration state, not the model.

        This is the state the production schema is actually built
        from, so it answers whether a column is really missing
        there, as opposed to merely missing from the model.
        """

        from django.db import connection
        from django.db.migrations.loader import MigrationLoader

        loader = MigrationLoader(
            connection,
            ignore_no_migrations=True,
        )

        state = loader.project_state(
            ('auth', '0001_initial')
        )

        model_state = state.models['auth', 'user']

        for field in ('username', 'email', 'is_staff',
                      'date_joined'):

            with self.subTest(field=field):

                self.assertIn(field, model_state.fields)

    def test_the_migrations_agree_with_the_models(self):
        """No pending migration, so no column is missing in production."""

        from django.apps import apps
        from django.db import connection
        from django.db.migrations.autodetector import (
            MigrationAutodetector,
        )
        from django.db.migrations.executor import MigrationExecutor
        from django.db.migrations.state import ProjectState

        executor = MigrationExecutor(connection)

        autodetector = MigrationAutodetector(
            executor.loader.project_state(),
            ProjectState.from_apps(apps),
        )

        changes = autodetector.changes(
            graph=executor.loader.graph,
            trim_to_apps=None,
            convert_apps=None,
            migration_name=None,
        )

        self.assertEqual(
            changes,
            {},
            msg=(
                'the models have moved ahead of the migrations, so '
                'production is missing a column the admin renders'
            ),
        )

    def test_the_task_models_still_have_the_fields_the_admin_uses(self):

        for model, fields in (
            (Task, ('title', 'user', 'subject', 'status',
                    'priority', 'due_date')),
            (Subject, ('name', 'user', 'updated_at', 'created_at')),
            (Note, ('title', 'user', 'subject', 'updated_at',
                    'created_at', 'attachment')),
        ):

            for field in fields:

                with self.subTest(
                    model=model.__name__,
                    field=field,
                ):

                    self.assertIsNotNone(
                        model._meta.get_field(field)
                    )
