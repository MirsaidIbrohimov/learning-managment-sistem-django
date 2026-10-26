from datetime import timedelta
from html import escape

from django import forms
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from accounts.models import CoinPricingSettings, CoinPurchaseDiscount, Message

from .topup_pricing import discount_label

DURATION_CHOICES = [('keep', 'Hozirgi muddat'), ('none', 'Muddatsiz'), ('1', '1 kun'), ('3', '3 kun'),
                    ('5', '5 kun'), ('7', '7 kun'), ('14', '14 kun'), ('30', '30 kun')]


class CoinRateForm(forms.ModelForm):
    som_per_coin = forms.IntegerField(min_value=1, max_value=1000000, label="1 coin narxi (so'm)")

    class Meta:
        model = CoinPricingSettings
        fields = ['som_per_coin']


class CoinDiscountForm(forms.ModelForm):
    name = forms.CharField(max_length=120, label='Chegirma nomi')
    discount_type = forms.ChoiceField(choices=CoinPurchaseDiscount._meta.get_field('discount_type').choices, label='Turi')
    value = forms.IntegerField(min_value=1, max_value=2147483647, label='Qiymati')
    min_coins = forms.IntegerField(min_value=1, max_value=2147483647, label='Eng kam coin miqdori')
    is_active = forms.BooleanField(required=False, label='Darhol yoqish va xabar berish')
    theme = forms.ChoiceField(choices=CoinPurchaseDiscount.THEME_CHOICES, required=False, label='Bayram bezagi')
    duration = forms.ChoiceField(choices=DURATION_CHOICES, required=False, label='Aksiya muddati')

    class Meta:
        model = CoinPurchaseDiscount
        fields = ['name', 'theme', 'discount_type', 'value', 'min_coins', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (self.instance.pk and self.instance.valid_until):
            self.fields['duration'].choices = DURATION_CHOICES[1:]
        self.fields['duration'].initial = 'keep' if self.instance.pk and self.instance.valid_until else 'none'

    def clean(self):
        data = super().clean()
        data['theme'] = data.get('theme') or 'celebration'
        kind, value, coins = data.get('discount_type'), data.get('value') or 0, data.get('min_coins') or 0
        if kind == 'percentage' and value > 99:
            self.add_error('value', 'Foiz 1 dan 99 gacha bo‘lishi kerak.')
        if kind == 'package':
            if coins < 1000:
                self.add_error('min_coins', 'Maxsus narx kamida 1 000 tanga uchun beriladi (eng kam xarid).')
            elif value >= coins * CoinPricingSettings.current().som_per_coin:
                self.add_error('value', 'Maxsus narx oddiy narxdan arzon bo‘lishi kerak.')
        data['duration'] = data.get('duration') or ('keep' if self.instance.valid_until else 'none')
        if data['duration'] == 'keep' and data.get('is_active') and self.instance.is_expired:
            self.add_error('duration', 'Aksiya muddati tugagan. Yangi muddat tanlang.')
        return data

    def save(self, commit=True):
        duration = self.cleaned_data['duration']
        if duration == 'none':
            self.instance.valid_until = None
        elif duration != 'keep':
            self.instance.valid_until = timezone.now() + timedelta(days=int(duration))
        return super().save(commit)


def announce(discount, sender):
    label = discount_label({'discount_type': discount.discount_type, 'value': discount.value,
                            'min_coins': discount.min_coins})
    if discount.discount_type == 'package':
        offer = f'{discount.name}: {label}! '
    else:
        offer = (f'{discount.name}: coin xaridiga {label} chegirma! '
                 f'Kamida {discount.min_coins} coin xarid qiling. ')
    until = (f'Aksiya {timezone.localtime(discount.valid_until):%d.%m.%Y %H:%M} gacha. '
             if discount.valid_until else '')
    content = (offer + until + 'Market → Tanga sotib olish bo‘limida chegirma avtomatik qo‘llanadi. '
               'Bir nechta aksiya orasidan eng foydalisi tanlanadi.')
    Message.objects.create(title='Coin xaridiga chegirma!', content=content,
                           message_type='all', sender=sender)
    from telegram_bot.utils import notify_group
    transaction.on_commit(lambda: notify_group(escape(content)))


def manage(request):
    """Called after the existing administrator permission check."""
    settings = CoinPricingSettings.current()
    rate_form = CoinRateForm(instance=settings)
    editing = None
    edit_id = request.GET.get('edit_coin')
    if edit_id and edit_id.isascii() and edit_id.isdigit():
        editing = get_object_or_404(CoinPurchaseDiscount, pk=int(edit_id))
    discount_form = CoinDiscountForm(instance=editing, initial={'min_coins': 1, 'theme': 'celebration'} if not editing else None)
    if request.method == 'POST':
        action = request.POST.get('coin_action')
        if action == 'rate':
            rate_form = CoinRateForm(request.POST, instance=settings)
            if rate_form.is_valid():
                rate_form.save()
                messages.success(request, f'Narx saqlandi: 1 tanga = {rate_form.instance.som_per_coin} so‘m. Marketdagi yangi xaridlar shu narxda hisoblanadi.')
                return redirect('admin_discounts')
        elif action in ('add', 'edit'):
            if action == 'edit':
                editing = get_object_or_404(CoinPurchaseDiscount, pk=request.POST.get('discount_id'))
            was_active = bool(editing and editing.is_active)
            discount_form = CoinDiscountForm(request.POST, instance=editing)
            if discount_form.is_valid():
                with transaction.atomic():
                    discount = discount_form.save()
                    if discount.is_active and (not was_active or discount_form.has_changed()):
                        announce(discount, request.user)
                messages.success(request, 'Coin chegirmasi saqlandi.')
                return redirect('admin_discounts')
        elif action in ('enable', 'disable'):
            with transaction.atomic():
                discount = get_object_or_404(CoinPurchaseDiscount, pk=request.POST.get('discount_id'))
                enabled = action == 'enable'
                if enabled and discount.is_expired:
                    messages.error(request, 'Aksiya muddati tugagan. «Tahrirlash» orqali yangi muddat tanlang.')
                    return redirect('admin_discounts')
                changed = CoinPurchaseDiscount.objects.filter(pk=discount.pk, is_active=not enabled).update(is_active=enabled)
                if changed and enabled:
                    announce(discount, request.user)
            messages.success(request, 'Coin chegirmasi yoqildi.' if enabled else 'Coin chegirmasi o‘chirildi.')
            return redirect('admin_discounts')
    discounts = list(CoinPurchaseDiscount.objects.all())
    return {'coin_rate_form': rate_form, 'coin_discount_form': discount_form, 'coin_editing': editing,
            'coin_discounts': discounts, 'coin_active_count': sum(d.is_active for d in discounts),
            'coin_rate': CoinPricingSettings.current().som_per_coin}
