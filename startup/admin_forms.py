"""Admin panel formalari.

`forms.py` ataylab `owner`, `status`, `progress`, `total_xp`, `current_stage`
maydonlarini chiqarib tashlagan (mass assignment himoyasi). Admin ularning
ikkitasini — `owner` va `status` — boshqarishi kerak, shuning uchun kengaytirish
shu alohida modulda: student formasi hech qachon bu maydonlarni ko'rmaydi.
"""

from django import forms
from django.contrib.auth import get_user_model

from .forms import StartupForm
from .models import Startup

User = get_user_model()


class StartupAdminForm(StartupForm):
    class Meta(StartupForm.Meta):
        fields = StartupForm.Meta.fields + ['owner', 'status']
        widgets = dict(StartupForm.Meta.widgets, **{
            'owner': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        })

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['owner'].queryset = (User.objects
                                         .filter(role='student')
                                         .only('id', 'username', 'first_name', 'last_name')
                                         .order_by('first_name', 'last_name'))

    def clean(self):
        cleaned = super().clean()
        owner = cleaned.get('owner')
        status = cleaned.get('status')

        # `Startup.Meta.constraints` da `startup_one_active_per_owner` bor —
        # bu yerda tekshirmasak, saqlashda IntegrityError → 500 bo'lardi.
        if owner and status == 'active':
            clash = Startup.objects.filter(owner=owner, status='active')
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            existing = clash.first()
            if existing:
                self.add_error('status', forms.ValidationError(
                    f'Bu oʻquvchida allaqachon faol startup bor: "{existing.name}". '
                    f'Avval uni toʻxtatilgan yoki arxivlangan holatga oʻtkazing.'
                ))
        return cleaned


class ManualXPForm(forms.Form):
    """Adminning qo'lda XP tuzatishi — izoh majburiy (audit uchun)."""

    amount = forms.IntegerField(min_value=1, max_value=10000, label='XP miqdori',
                                widget=forms.NumberInput(attrs={'class': 'form-control'}))
    description = forms.CharField(max_length=200, label='Sabab',
                                  widget=forms.TextInput(attrs={'class': 'form-control'}))
