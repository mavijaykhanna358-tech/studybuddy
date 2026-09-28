from django import forms
from django.utils import timezone

from .models import Note, Subject, Task


# ============================================================
# SUBJECT FORM
# ============================================================

class SubjectForm(forms.ModelForm):

    def __init__(
        self,
        *args,
        user=None,
        **kwargs
    ):

        super().__init__(
            *args,
            **kwargs
        )

        self.user = user

    class Meta:
        model = Subject

        fields = [
            'name',
            'description'
        ]

        widgets = {
            'name': forms.TextInput(
                attrs={
                    'class': 'sb-input',
                    'placeholder': 'e.g. Mathematics',
                    'autocomplete': 'off',
                    'maxlength': 100,
                }
            ),

            'description': forms.Textarea(
                attrs={
                    'class': 'sb-textarea',
                    'rows': 3,
                    'placeholder': 'Optional description',
                    'maxlength': 1000,
                }
            ),
        }

    def clean_name(self):

        name = self.cleaned_data.get(
            'name',
            ''
        ).strip()

        if not name:
            raise forms.ValidationError(
                'Subject name is required.'
            )

        if len(name) > 100:
            raise forms.ValidationError(
                'Subject name must be 100 characters or fewer.'
            )

        # A unique constraint on (user, name) exists at the database
        # level. Checking here turns a possible IntegrityError into
        # a readable message.

        duplicates = Subject.objects.filter(
            name__iexact=name
        )

        # Only the current user's subjects matter, so another
        # student using the same subject name is not blocked.

        if self.user is not None:

            duplicates = duplicates.filter(
                user=self.user
            )

        if self.instance.pk:

            duplicates = duplicates.exclude(
                pk=self.instance.pk
            )

        if duplicates.exists():

            raise forms.ValidationError(
                'You already have a subject with this name.'
            )

        return name


# ============================================================
# TASK FORM
# ============================================================

class TaskForm(forms.ModelForm):

    class Meta:
        model = Task

        fields = [
            'subject',
            'title',
            'description',
            'due_date',
            'priority',
            'status'
        ]

        widgets = {

            'subject': forms.Select(
                attrs={
                    'class': 'sb-select'
                }
            ),

            'title': forms.TextInput(
                attrs={
                    'class': 'sb-input',
                    'placeholder': 'Task title',
                    'maxlength': 200,
                }
            ),

            'description': forms.Textarea(
                attrs={
                    'class': 'sb-textarea',
                    'rows': 4,
                    'placeholder': 'Add details',
                    'maxlength': 2000,
                }
            ),

            'due_date': forms.DateInput(
                attrs={
                    'class': 'sb-input',
                    'type': 'date'
                }
            ),

            'priority': forms.Select(
                attrs={
                    'class': 'sb-select'
                }
            ),

            'status': forms.Select(
                attrs={
                    'class': 'sb-select'
                }
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        **kwargs
    ):

        super().__init__(
            *args,
            **kwargs
        )

        self.user = user

        # Change --------- to Select Subject
        self.fields['subject'].empty_label = 'Select Subject'

        # Show only subjects belonging to
        # the currently logged-in user
        if user is not None:

            self.fields['subject'].queryset = (
                Subject.objects
                .filter(user=user)
                .order_by('name')
            )

        # Prevent selecting past dates
        # when creating a new task
        today = timezone.localdate()

        if not self.instance.pk:

            self.fields['due_date'].widget.attrs[
                'min'
            ] = today.isoformat()

    def clean_title(self):

        title = self.cleaned_data.get(
            'title',
            ''
        ).strip()

        if not title:

            raise forms.ValidationError(
                'Title is required.'
            )

        if len(title) > 200:

            raise forms.ValidationError(
                'Title must be 200 characters or fewer.'
            )

        return title

    def clean(self):

        cleaned_data = super().clean()

        subject = cleaned_data.get(
            'subject'
        )

        due_date = cleaned_data.get(
            'due_date'
        )

        # Make sure the selected subject
        # belongs to the logged-in user
        if (
            subject
            and self.user
            and subject.user != self.user
        ):

            self.add_error(
                'subject',
                'Please select one of your subjects.'
            )

        # Do not allow past dates for new tasks
        if (
            not self.instance.pk
            and due_date
            and due_date < timezone.localdate()
        ):

            self.add_error(
                'due_date',
                'Due date cannot be before today.'
            )

        return cleaned_data


# ============================================================
# NOTE FORM
# ============================================================

class NoteForm(forms.ModelForm):

    # 25 MB. Large enough for scanned notes and slide decks,
    # small enough to reject accidental video uploads.

    MAX_ATTACHMENT_SIZE = (
        25 * 1024 * 1024
    )

    ALLOWED_ATTACHMENT_EXTENSIONS = [
        # Images
        'jpg',
        'jpeg',
        'png',
        'gif',
        'webp',
        'bmp',
        'svg',

        # Documents
        'pdf',
        'doc',
        'docx',
        'xls',
        'xlsx',
        'ppt',
        'pptx',
        'txt',
        'csv',
        'md',
        'rtf',
    ]

    attachment = forms.FileField(
        required=False,
        help_text=(
            'Optional. PDF, Word, Excel, PowerPoint, text or '
            'image files up to 25 MB.'
        ),
    )

    class Meta:
        model = Note

        fields = [
            'subject',
            'title',
            'content',
            'attachment'
        ]

        widgets = {

            'subject': forms.Select(
                attrs={
                    'class': 'sb-select'
                }
            ),

            'title': forms.TextInput(
                attrs={
                    'class': 'sb-input',
                    'placeholder': 'Note title',
                    'maxlength': 200,
                }
            ),

            'content': forms.Textarea(
                attrs={
                    'class': 'sb-textarea',
                    'rows': 6,
                    'placeholder': 'Write your note here...',
                }
            ),

            'attachment': forms.ClearableFileInput(
                attrs={
                    'class': 'sb-input',
                    'accept': (
                        'image/*,'
                        '.pdf,'
                        '.doc,'
                        '.docx,'
                        '.txt,'
                        '.md,'
                        '.csv,'
                        '.rtf,'
                        '.ppt,'
                        '.pptx,'
                        '.xls,'
                        '.xlsx'
                    )
                }
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        **kwargs
    ):

        super().__init__(
            *args,
            **kwargs
        )

        self.user = user

        # Show only the user's subjects
        self.fields['subject'].empty_label = 'Select Subject'

        if user is not None:

            self.fields['subject'].queryset = (
                Subject.objects
                .filter(user=user)
                .order_by('name')
            )

    def clean_attachment(self):

        attachment = self.cleaned_data.get(
            'attachment'
        )

        if not attachment:
            return attachment

        name_parts = attachment.name.rsplit(
            '.',
            1
        )

        extension = (
            name_parts[-1].lower()
            if len(name_parts) == 2
            else ''
        )

        if extension not in self.ALLOWED_ATTACHMENT_EXTENSIONS:

            allowed = ', '.join(
                sorted(
                    set(
                        self.ALLOWED_ATTACHMENT_EXTENSIONS
                    )
                )
            )

            raise forms.ValidationError(
                f'That file type is not supported. '
                f'Allowed types: {allowed}.'
            )

        if attachment.size > self.MAX_ATTACHMENT_SIZE:

            raise forms.ValidationError(
                'File is too large. '
                'Maximum size is 25 MB.'
            )

        return attachment

    def clean_title(self):

        title = self.cleaned_data.get(
            'title',
            ''
        ).strip()

        if not title:

            raise forms.ValidationError(
                'Title is required.'
            )

        if len(title) > 200:

            raise forms.ValidationError(
                'Title must be 200 characters or fewer.'
            )

        return title

    def clean_content(self):

        content = self.cleaned_data.get(
            'content',
            ''
        ).strip()

        if not content:

            raise forms.ValidationError(
                'Note content is required.'
            )

        return content

    def clean(self):

        cleaned_data = super().clean()

        subject = cleaned_data.get(
            'subject'
        )

        # Security check
        if (
            subject
            and self.user
            and subject.user != self.user
        ):

            self.add_error(
                'subject',
                'Please select one of your subjects.'
            )

        return cleaned_data