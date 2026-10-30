"""🎟 Promo kodlar: öquvçi sahifasi, chek, admin nazorati."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from . import promo as promo_rules
from .models import PromoCode, PromoRedemption


def _back(request, default='coin:promo_codes'):
    nxt = request.POST.get('next', '')
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect(default)


@login_required
def promo_codes_page(request):
    user = request.user
    member = promo_rules.is_promo_member(user)
    my_code = promo_rules.current_code(user) if member else None
    return render(request, 'coin/market/promo_codes.html', {
        'member': member,
        'my_code': my_code,
        'my_code_users': my_code.redemptions.select_related('user') if my_code else [],
        'past_codes': user.promo_codes.prefetch_related('redemptions__user')[:6] if member else [],
        'my_redemptions': user.promo_redemptions.select_related('promo__owner')[:10],
        'next_redeem_at': promo_rules.next_redeem_at(user) if member else None,
        'rules': {'uses': promo_rules.CODE_USES, 'days': promo_rules.CODE_DAYS,
                  'min': promo_rules.COINS_RANGE[0], 'max': promo_rules.COINS_RANGE[1],
                  'cooldown': promo_rules.REDEEM_COOLDOWN_DAYS},
    })


@login_required
def promo_redeem(request):
    if request.method != 'POST':
        return redirect('coin:promo_codes')
    from .models import CoinPricePromo
    if CoinPricePromo.objects.filter(code=promo_rules.normalize(request.POST.get('code'))).exists():
        return coin_promo_activate(request)  # coin narx kodi kiritilgan — marketdagi paketga yönaltiramiz
    redemption, msg = promo_rules.redeem(request.user, request.POST.get('code'))
    if redemption is None:
        messages.error(request, msg)
        return _back(request)
    messages.success(request, msg)
    return redirect('coin:promo_receipt', pk=redemption.pk)


@login_required
def coin_promo_activate(request):
    """💸 Coin narx promo kodini faollaştiriş — paket marketda maxsus narxda paydo böladi."""
    from .coin_promo import activate
    if request.method == 'POST':
        activation, msg = activate(request.user, request.POST.get('code'))
        (messages.success if activation else messages.error)(request, msg)
    return redirect(reverse('coin:market_list') + '#coin-topup')


@login_required
def promo_receipt(request, pk):
    redemption = get_object_or_404(PromoRedemption.objects.select_related('promo__owner', 'user'), pk=pk)
    if redemption.user_id != request.user.pk and not request.user.is_admin:
        raise Http404
    return render(request, 'coin/market/promo_receipt.html', {'r': redemption})


# ============== ADMIN ==============

@login_required
def admin_promo_codes(request):
    if not request.user.is_admin:
        return redirect('home')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            def num(name, default):
                try:
                    return int(request.POST.get(name) or default)
                except (TypeError, ValueError):
                    return -1
            promo, msg = promo_rules.create_admin_code(
                request.user, code=request.POST.get('code', ''),
                max_uses=num('max_uses', promo_rules.CODE_USES), days=num('days', promo_rules.CODE_DAYS),
                min_coins=num('min_coins', promo_rules.COINS_RANGE[0]),
                max_coins=num('max_coins', promo_rules.COINS_RANGE[1]),
            )
            (messages.success if promo else messages.error)(request, msg)
        elif action == 'toggle':
            promo = get_object_or_404(PromoCode, pk=request.POST.get('promo_id') or 0)
            promo.is_active = not promo.is_active
            promo.save(update_fields=['is_active'])
            messages.success(request, f"{promo.code} {'yoqildi' if promo.is_active else 'öçirildi'}.")
        elif action == 'price_create':
            from .coin_promo import create_promo

            def num(name):
                try:
                    return int((request.POST.get(name) or '').replace(' ', ''))
                except ValueError:
                    return -1
            promo, msg = create_promo(
                request.user, code=request.POST.get('code', ''), title=request.POST.get('title', ''),
                coins=num('coins'), price_regular=num('price_regular'), price_premium=num('price_premium'),
                days=num('days'), max_uses=max(0, num('max_uses')),
            )
            (messages.success if promo else messages.error)(request, msg)
        elif action == 'price_toggle':
            from .models import CoinPricePromo
            promo = get_object_or_404(CoinPricePromo, pk=request.POST.get('promo_id') or 0)
            promo.is_active = not promo.is_active
            promo.save(update_fields=['is_active'])
            messages.success(request, f"{promo.code} {'yoqildi' if promo.is_active else 'öçirildi'}.")
        return redirect(request.get_full_path())

    now = timezone.now()
    qs = PromoCode.objects.select_related('owner', 'created_by').annotate(
        used=Count('redemptions'), given=Sum('redemptions__coins'))
    status = request.GET.get('status', 'all')
    kind = request.GET.get('kind', 'all')
    search = request.GET.get('q', '').strip()
    if status == 'active':
        qs = qs.filter(is_active=True, expires_at__gt=now)
    elif status == 'expired':
        qs = qs.filter(Q(expires_at__lte=now) | Q(is_active=False))
    if kind == 'student':
        qs = qs.filter(owner__isnull=False)
    elif kind == 'admin':
        qs = qs.filter(owner__isnull=True)
    if search:
        qs = qs.filter(Q(code__icontains=search) | Q(owner__first_name__icontains=search) |
                       Q(owner__last_name__icontains=search) | Q(owner__username__icontains=search) |
                       Q(redemptions__user__username__icontains=search)).distinct()

    totals = PromoRedemption.objects.aggregate(count=Count('id'), coins=Sum('coins'))
    page = Paginator(qs, 30).get_page(request.GET.get('page'))
    for p in page:
        p.users = list(p.redemptions.select_related('user'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'coin/admin/promo_codes.html', {
        'page_obj': page,
        'stats': {
            'total': PromoCode.objects.count(),
            'active': PromoCode.objects.filter(is_active=True, expires_at__gt=now).count(),
            'redemptions': totals['count'] or 0,
            'coins': totals['coins'] or 0,
        },
        'status': status, 'kind': kind, 'q': search,
        'query_string': params.urlencode(),
        'defaults': {'uses': promo_rules.CODE_USES, 'days': promo_rules.CODE_DAYS,
                     'min': promo_rules.COINS_RANGE[0], 'max': promo_rules.COINS_RANGE[1]},
        'price_promos': _price_promo_rows(),
        'coin_rate': _coin_rate(),
    })


def _coin_rate():
    from accounts.models import CoinPricingSettings
    return CoinPricingSettings.current().som_per_coin


def _price_promo_rows():
    from .models import CoinPricePromo
    rows = list(CoinPricePromo.objects.select_related('created_by').annotate(
        activated=Count('activations'), bought=Count('activations', filter=Q(activations__used_at__isnull=False)),
        revenue=Sum('activations__paid_som'))[:50])
    rate = _coin_rate()
    for p in rows:
        p.gross = p.coins * rate
        p.premium_gross = (p.gross + 1) // 2
        p.buyers = list(p.activations.filter(used_at__isnull=False).select_related('user').order_by('-used_at'))
    return rows
