"""Admin: kurs chegirmasi formasi (masalan 90 000 so'mlik kurs 3 kun 50 000 so'm)."""
from datetime import timedelta
from html import escape

from django import forms
from django.db import transaction
from django.utils import timezone

from .course_pricing import MIN_COURSE_PRICE
from .models import Discount, Message, Profession

DURATION_CHOICES = [('1', '1 kun'), ('3', '3 kun'), ('5', '5 kun'), ('7', '7 kun'), ('14', '14 kun'),
                    ('30', '30 kun'), ('custom', 'Sanani o‘zim belgilayman'), ('none', 'Muddatsiz')]
DATETIME_INPUT = forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}, format='%Y-%m-%dT%H:%M')


def _money(value):
    return f'{value:,}'.replace(',', ' ')


class CourseDiscountForm(forms.ModelForm):
    discount_type = forms.ChoiceField(choices=Discount.DISCOUNT_TYPES, initial='price', label='Chegirma turi',
                                      widget=forms.Select(attrs={'class': 'form-select'}))
    discount_value = forms.IntegerField(min_value=1, max_value=2147483647, label='Qiymati',
                                        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1}))
    profession = forms.ModelChoiceField(queryset=Profession.objects.none(), required=False, label='Kurs',
                                        empty_label='Barcha sotuvdagi kurslar',
                                        widget=forms.Select(attrs={'class': 'form-select'}))
    duration = forms.ChoiceField(choices=DURATION_CHOICES, initial='3', label='Muddat')
    valid_from = forms.DateTimeField(required=False, label='Boshlanish', widget=DATETIME_INPUT,
                                     input_formats=['%Y-%m-%dT%H:%M'])
    valid_until = forms.DateTimeField(required=False, label='Tugash', widget=DATETIME_INPUT,
                                      input_formats=['%Y-%m-%dT%H:%M'])
    announce = forms.BooleanField(required=False, label='Saytda va Telegram guruhida e’lon qilish')

    class Meta:
        model = Discount
        fields = ['name', 'description', 'discount_type', 'discount_value', 'profession', 'is_active',
                  'valid_from', 'valid_until']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control form-control-lg',
                                           'placeholder': 'Masalan: Kuzgi chegirma'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        sold = Profession.objects.filter(is_paid=True, one_time_payment=True, one_time_price__gt=0)
        if self.instance.profession_id:
            sold = sold | Profession.objects.filter(pk=self.instance.profession_id)
        self.fields['profession'].queryset = sold.order_by('name')
        if self.instance.pk:
            # Tahrirda mavjud sanalar saqlanadi, agar admin yangi muddat tanlamasa.
            self.fields['duration'].initial = 'custom' if self.instance.valid_until else 'none'

    def clean(self):
        data = super().clean()
        kind, value, course = data.get('discount_type'), data.get('discount_value'), data.get('profession')
        if not value:
            return data
        if kind == 'percentage' and value > 99:
            self.add_error('discount_value', 'Foiz 1 dan 99 gacha bo‘lishi kerak.')
        if kind == 'price' and not course:
            self.add_error('profession', '«Yangi narx» uchun bitta kursni tanlang.')
        if course:
            if not course.is_sold_once:
                self.add_error('profession', 'Bu kurs bir martalik to‘lov bilan sotilmaydi.')
            else:
                original = int(course.one_time_price)
                raw = value if kind == 'price' else original - (
                    original * min(value, 99) // 100 if kind == 'percentage' else value)
                if raw < MIN_COURSE_PRICE:
                    self.add_error('discount_value', f'Chegirmali narx kamida {_money(MIN_COURSE_PRICE)} so‘m bo‘lishi kerak.')
                elif raw >= original:
                    self.add_error('discount_value', f'Chegirmali narx asl narxdan ({_money(original)} so‘m) kam bo‘lishi kerak.')

        now = timezone.now()
        duration = data.get('duration')
        if duration == 'none':
            data['valid_from'] = data['valid_until'] = None
        elif duration and duration != 'custom':
            data['valid_from'] = now
            data['valid_until'] = now + timedelta(days=int(duration))
        elif duration == 'custom':
            start, end = data.get('valid_from'), data.get('valid_until')
            if not end:
                self.add_error('valid_until', 'Tugash sanasini kiriting.')
            elif start and end <= start:
                self.add_error('valid_until', 'Tugash vaqti boshlanishdan keyin bo‘lishi kerak.')
            elif data.get('is_active') and end <= now:
                self.add_error('valid_until', 'Bu sana o‘tib ketgan. Yangi tugash vaqtini tanlang.')
        return data


def announce(discount, sender):
    course = discount.profession
    if discount.discount_type == 'price' and course:
        offer = f"'{course.name}' kursi {_money(course.one_time_price)} emas, atigi {_money(discount.discount_value)} so‘m!"
    elif discount.discount_type == 'percentage':
        offer = f"{course.name + ' kursiga' if course else 'Kurslarga'} {discount.discount_value}% chegirma!"
    else:
        offer = f"{course.name + ' kursiga' if course else 'Kurslarga'} {_money(discount.discount_value)} so‘m chegirma!"
    until = (f" Chegirma {timezone.localtime(discount.valid_until):%d.%m.%Y %H:%M} gacha amal qiladi."
             if discount.valid_until else '')
    content = f'{discount.name}: {offer}{until} «Kurslar» bo‘limida sotib oling.'
    Message.objects.create(title='Kursga chegirma!', content=content, message_type='all', sender=sender)
    from telegram_bot.utils import notify_group
    text, keyboard = _telegram_post(discount)
    transaction.on_commit(lambda: notify_group(text, inline_keyboard=keyboard))


def _telegram_post(discount):
    """Telegram guruhi uchun marketing uslubidagi HTML xabar va «Sotib olish» tugmasi."""
    course = discount.profession
    title = f'🎓 <b>«{escape(course.name)}»</b> kursi' if course else '🎓 <b>Barcha kurslarimizga</b>'
    lines = ['🔥🔥 <b>KATTA CHEGIRMA!</b> 🔥🔥', f'🏷 <i>{escape(discount.name)}</i>', '━━━━━━━━━━━━━━━', '', title, '']
    if discount.discount_type == 'price' and course:
        old, new = course.one_time_price, discount.discount_value
        lines += [f'❌ Oddiy narx: <s>{_money(old)} so‘m</s>',
                  f'✅ Hozir atigi: <b>{_money(new)} so‘m</b>']
        if old > new:
            lines.append(f'💰 Tejaysiz: <b>{_money(old - new)} so‘m (−{round((old - new) * 100 / old)}%)</b>')
    elif discount.discount_type == 'percentage':
        lines.append(f'💥 <b>−{discount.discount_value}% chegirma!</b>')
    else:
        lines.append(f'💥 <b>{_money(discount.discount_value)} so‘m chegirma!</b>')
    lines.append('')
    if discount.valid_until:
        lines.append(f'⏳ Taklif faqat <b>{timezone.localtime(discount.valid_until):%d.%m.%Y %H:%M}</b> gacha!')
    lines += ['🚀 Imkoniyatni qo‘ldan boy bermang — bilimingizga bugun sarmoya kiriting!', '',
              '👉 <b>«Kurslar»</b> bo‘limida hoziroq sotib oling!']

    from django.conf import settings
    from django.urls import reverse
    site = getattr(settings, 'SITE_URL', '')
    if not site.startswith('https://'):
        return '\n'.join(lines), None
    path = reverse('public_course_short', args=[course.pk]) if course else reverse('public_courses')
    return '\n'.join(lines), [[{'text': '🛒 Hoziroq sotib olish', 'url': site + path}]]
