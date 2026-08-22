"""Formalar — mass assignment himoyasi: har bir forma `fields` ni aniq
sanab beradi, `owner`, `status`, `total_xp`, `progress`, `current_stage`
hech qachon foydalanuvchi kiritishidan olinmaydi.
"""

from django import forms
from django.contrib.auth import get_user_model

from .models import (
    MEMBER_ROLE_CHOICES,
    METRIC_KEY_CHOICES,
    PitchDeck,
    Startup,
    StartupFeedback,
    StartupFinance,
    StartupMetric,
    StartupTask,
    StartupTaskSubmission,
)


class StartupForm(forms.ModelForm):
    class Meta:
        model = Startup
        fields = [
            'name', 'logo', 'category', 'profession', 'short_description',
            'description', 'problem', 'solution', 'target_audience',
            'business_model', 'competitors',
            'website', 'github_url', 'telegram_url', 'instagram_url',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control',
                                           'placeholder': 'Masalan: SmartAgro'}),
            'logo': forms.ClearableFileInput(attrs={'class': 'form-control',
                                                    'accept': 'image/*'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'profession': forms.Select(attrs={'class': 'form-select'}),
            'short_description': forms.TextInput(attrs={
                'class': 'form-control', 'maxlength': 300,
                'placeholder': 'Bir gapda: startup nima qiladi?'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'problem': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'solution': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'target_audience': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'business_model': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'competitors': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'website': forms.URLInput(attrs={'class': 'form-control',
                                              'placeholder': 'https://'}),
            'github_url': forms.URLInput(attrs={'class': 'form-control',
                                                 'placeholder': 'https://github.com/...'}),
            'telegram_url': forms.URLInput(attrs={'class': 'form-control',
                                                  'placeholder': 'https://t.me/...'}),
            'instagram_url': forms.URLInput(attrs={'class': 'form-control',
                                                   'placeholder': 'https://instagram.com/...'}),
        }

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if len(name) < 3:
            raise forms.ValidationError('Startup nomi kamida 3 belgidan iborat boʻlishi kerak.')
        return name


class StartupTaskForm(forms.ModelForm):
    class Meta:
        model = StartupTask
        fields = ['stage', 'title', 'description', 'assigned_to', 'deadline',
                  'priority', 'points', 'attachment']
        widgets = {
            'stage': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'deadline': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'points': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 500}),
            'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, startup=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.startup = startup
        if startup is not None:
            # Faqat shu startupning bosqichlari va faol a'zolari — boshqa
            # startup ID'sini POST qilib yuborish imkonsiz.
            self.fields['stage'].queryset = startup.stages.all()
            self.fields['stage'].required = True
            self.fields['assigned_to'].queryset = get_user_model().objects.filter(
                startup_memberships__startup=startup,
                startup_memberships__status='active',
            ).distinct()
            self.fields['assigned_to'].required = False


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = StartupTaskSubmission
        fields = ['description', 'file', 'link', 'github_url', 'demo_url']
        widgets = {
            'description': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'Nima qildingiz? Natijani qisqacha yozing.'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://'}),
            'github_url': forms.URLInput(attrs={'class': 'form-control',
                                                 'placeholder': 'https://github.com/...'}),
            'demo_url': forms.URLInput(attrs={'class': 'form-control',
                                              'placeholder': 'https://demo...'}),
        }

    def clean(self):
        cleaned = super().clean()
        has_any = any([
            cleaned.get('description', '').strip(),
            cleaned.get('file'),
            cleaned.get('link'),
            cleaned.get('github_url'),
            cleaned.get('demo_url'),
        ])
        if not has_any:
            raise forms.ValidationError(
                'Kamida bittasini toʻldiring: izoh, fayl, havola, GitHub yoki demo.')
        return cleaned


class InviteForm(forms.Form):
    """Jamoaga taklif — foydalanuvchi aniq `username` bo'yicha topiladi.

    Ataylab qidiruv/autocomplete emas: aks holda butun foydalanuvchi bazasini
    sanab chiqish (enumeration) imkoni paydo bo'ladi.
    """

    username = forms.CharField(
        max_length=150, label='Login (username)',
        widget=forms.TextInput(attrs={'class': 'form-control',
                                      'placeholder': 'Masalan: ali_valiev'}))
    role = forms.ChoiceField(
        choices=MEMBER_ROLE_CHOICES, initial='member', label='Rol',
        widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, startup=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.startup = startup

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        user = get_user_model().objects.filter(username__iexact=username).first()
        if user is None:
            raise forms.ValidationError('Bunday loginli foydalanuvchi topilmadi.')
        if self.startup is not None and user.id == self.startup.owner_id:
            raise forms.ValidationError('Startup egasi allaqachon jamoada.')
        self.cleaned_data['user'] = user
        return username


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = StartupFeedback
        fields = ['message', 'rating']
        widgets = {
            'message': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Nima yaxshi, nimani yaxshilash kerak?'}),
            'rating': forms.Select(
                choices=[('', 'Baho (ixtiyoriy)')] + [(n, '★' * n) for n in range(1, 6)],
                attrs={'class': 'form-select'}),
        }

    def clean_message(self):
        message = self.cleaned_data['message'].strip()
        if len(message) < 5:
            raise forms.ValidationError('Fikr kamida 5 belgidan iborat boʻlishi kerak.')
        return message


class FinanceForm(forms.ModelForm):
    class Meta:
        model = StartupFinance
        fields = ['type', 'amount', 'description', 'date']
        widgets = {
            'type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'min': 1,
                                               'step': 1, 'placeholder': '0'}),
            'description': forms.TextInput(attrs={'class': 'form-control',
                                                  'placeholder': 'Nima uchun?'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError('Summa 0 dan katta boʻlishi kerak.')
        return amount


class MetricForm(forms.ModelForm):
    key = forms.ChoiceField(choices=METRIC_KEY_CHOICES, label='Koʻrsatkich',
                            widget=forms.Select(attrs={'class': 'form-select'}))

    class Meta:
        model = StartupMetric
        fields = ['key', 'value', 'date', 'note']
        widgets = {
            'value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'note': forms.TextInput(attrs={'class': 'form-control',
                                           'placeholder': 'Izoh (ixtiyoriy)'}),
        }

    def clean_value(self):
        value = self.cleaned_data['value']
        if value < 0:
            raise forms.ValidationError('Qiymat manfiy boʻlmasligi kerak.')
        return value


class PitchDeckForm(forms.ModelForm):
    class Meta:
        model = PitchDeck
        fields = list(PitchDeck.SECTION_FIELDS)
        widgets = {
            field: forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
            for field in PitchDeck.SECTION_FIELDS
        }
