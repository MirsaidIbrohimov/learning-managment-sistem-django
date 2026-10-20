from html import escape

from django import forms
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect

from accounts.models import CoinPricingSettings, CoinPurchaseDiscount, Message


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

    class Meta:
        model = CoinPurchaseDiscount
        fields = ['name', 'theme', 'discount_type', 'value', 'min_coins', 'is_active']

    def clean(self):
        data = super().clean()
        data['theme'] = data.get('theme') or 'celebration'
        if data.get('discount_type') == 'percentage' and data.get('value', 0) > 99:
            self.add_error('value', 'Foiz 1 dan 99 gacha bo‘lishi kerak.')
        return data


def announce(discount, sender):
    unit = '%' if discount.discount_type == 'percentage' else " so‘m"
    content = (f'{discount.name}: coin xaridiga {discount.value}{unit} chegirma! '
               f'Kamida {discount.min_coins} coin xarid qiling. '
               'Market → Tanga sotib olish bo‘limida chegirma avtomatik qo‘llanadi. '
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
                changed = CoinPurchaseDiscount.objects.filter(pk=discount.pk, is_active=not enabled).update(is_active=enabled)
                if changed and enabled:
                    announce(discount, request.user)
            messages.success(request, 'Coin chegirmasi yoqildi.' if enabled else 'Coin chegirmasi o‘chirildi.')
            return redirect('admin_discounts')
    discounts = list(CoinPurchaseDiscount.objects.all())
    return {'coin_rate_form': rate_form, 'coin_discount_form': discount_form, 'coin_editing': editing,
            'coin_discounts': discounts, 'coin_active_count': sum(d.is_active for d in discounts),
            'coin_rate': CoinPricingSettings.current().som_per_coin}
