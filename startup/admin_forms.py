"""Admin panel formalari.

`forms.py` ataylab `owner`, `status`, `progress`, `total_xp`, `current_stage`
maydonlarini çiqarib taşlagan (mass assignment himoyasi). Admin ularning
ikkitasini — `owner` va `status` — boşqarişi kerak, şuning uçun kengaytiriş
şu alohida modulda: student formasi heç qaçon bu maydonlarni körmaydi.
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
        # bu yerda tekşirmasak, saqlaşda IntegrityError → 500 bölardi.
        if owner and status == 'active':
            clash = Startup.objects.filter(owner=owner, status='active')
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            existing = clash.first()
            if existing:
                self.add_error('status', forms.ValidationError(
                    f'Bu öquvçida allaqaçon faol startup bor: "{existing.name}". '
                    f'Avval uni töxtatilgan yoki arxivlangan holatga ötkazing.'
                ))
        return cleaned


class ManualXPForm(forms.Form):
    """Adminning qölda XP tuzatişi — izoh majburiy (audit uçun)."""

    amount = forms.IntegerField(min_value=1, max_value=10000, label='XP miqdori',
                                widget=forms.NumberInput(attrs={'class': 'form-control'}))
    description = forms.CharField(max_length=200, label='Sabab',
                                  widget=forms.TextInput(attrs={'class': 'form-control'}))
