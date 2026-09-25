from django import forms
from django.utils import timezone

from .models import Note, Subject, Task


# ============================================================
# SUBJECT FORM
# ============================================================

class SubjectForm(forms.ModelForm):

    class Meta:
        model = Subject

        fields = [
            'name',
            'description'
        ]

        widgets = {
            'name': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'e.g. Mathematics'
                }
            ),

            'description': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Optional description'
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
                    'class': 'form-select'
                }
            ),

            'title': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Task title'
                }
            ),

            'description': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 4,
                    'placeholder': 'Add details'
                }
            ),

            'due_date': forms.DateInput(
                attrs={
                    'class': 'form-control',
                    'type': 'date'
                }
            ),

            'priority': forms.Select(
                attrs={
                    'class': 'form-select'
                }
            ),

            'status': forms.Select(
                attrs={
                    'class': 'form-select'
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
                    'class': 'form-select'
                }
            ),

            'title': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Note title'
                }
            ),

            'content': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 6,
                    'placeholder': 'Write your note here...'
                }
            ),

            'attachment': forms.ClearableFileInput(
                attrs={
                    'class': 'form-control',
                    'accept': (
                        'image/*,'
                        '.pdf,'
                        '.doc,'
                        '.docx,'
                        '.txt,'
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

    def clean_title(self):

        title = self.cleaned_data.get(
            'title',
            ''
        ).strip()

        if not title:

            raise forms.ValidationError(
                'Title is required.'
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