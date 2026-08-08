from django import forms

from .models import ScheduledShift


class ScheduledShiftForm(forms.ModelForm):
    class Meta:
        model = ScheduledShift
        fields = ('employee', 'scheduled_date', 'start_time', 'end_time', 'notes')
        widgets = {
            'scheduled_date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only schedulable users are active ones — don't show deactivated accounts
        from apps.users.models import User
        self.fields['employee'].queryset = (
            User.objects.active_staff().order_by('first_name', 'last_name')
        )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_time')
        end = cleaned.get('end_time')
        if start and end and end <= start:
            self.add_error('end_time', "End time must be after start time.")
        return cleaned
