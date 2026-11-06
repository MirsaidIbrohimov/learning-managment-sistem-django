import math
from datetime import timedelta, datetime
from django.db import models as db_models
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Sum
from django.views.decorators.cache import never_cache
from accounts.models import CustomUser, PremiumRequest, Message
from .models import (
    Product, ProductLike, ProductComment, ProductPurchase, 
    CoinTransaction, ActivityLog, CoinTransfer
)
from telegram_bot.utils import notify_group, notify_user, notify_admins


# ============== FRONTEND PAGES (API-backed) ==============

@login_required
def coin_history(request):
    """Coin tarixi sahifasi — data API orqali yuklanadi"""
    return render(request, 'coin/coin_history.html')


@login_required
def coin_transfer(request):
    """Coin ötkazma sahifasi — alohida sahifa"""
    return render(request, 'coin/transfer.html')


@login_required
@never_cache
def market_list(request):
    """Market sahifasi — data API orqali yuklanadi"""
    from .payments import market_context
    context = market_context(request.user)
    if request.GET.get('coin_order'):
        from accounts.models import TezCheckPaymentOrder
        raw = request.GET['coin_order']
        if not raw.isascii() or not raw.isdigit() or len(raw) > 18:
            from django.http import Http404
            raise Http404
        context['coin_return_order'] = get_object_or_404(
            TezCheckPaymentOrder, pk=int(raw), student=request.user, purpose='coins')
    return render(request, 'coin/market/list.html', context)


@login_required
def legacy_market_redirect(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return redirect('coin:market_detail', token=product.token, permanent=True)


@login_required
def market_detail(request, token):
    """Mahsulot detail sahifasi — data API orqali yuklanadi"""
    product = get_object_or_404(Product.objects.only('pk'), token=token)
    return render(request, 'coin/market/detail.html', {'product_id': product.pk})


@login_required
def my_purchases(request):
    """Mening xaridlarim sahifasi — data API orqali yuklanadi"""
    return render(request, 'coin/market/my_purchases.html')


@login_required
def premium_page(request):
    """Premium sahifasi — data API orqali yuklanadi"""
    return render(request, 'coin/market/premium.html')


@login_required
def buy_premium_page(request):
    """Premium xarid landing — marketing sahifasi"""
    return render(request, 'coin/market/buy_premium.html')


@login_required
def extend_premium_page(request):
    """Premium uzaytiriş sahifasi"""
    return render(request, 'coin/market/extend_premium.html')


@login_required
def gift_premium_page(request):
    """Premiumni boşqa öquvçiga coin evaziga sovğa qiliş.

    1) start — qabul qiluvçi va tarif tekşiriladi, sovğa sessiyada tasdiqlaşni kutadi
       (Telegram tanlansa kod yuboriladi); 2) confirm — parol/kod töğri bölsa darhol bajariladi.
    """
    from accounts.course_membership import find_student
    from api.coin.views import can_user_buy_premium, get_premium_plans_for_user
    from . import premium_gift

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'start':
            recipient = find_student(request.POST.get('recipient'))
            ok, msg = premium_gift.start_gift(request, recipient, request.POST.get('plan', ''),
                                              request.POST.get('method', ''))
            (messages.info if ok else messages.error)(request, msg)
        elif action == 'confirm':
            ok, msg = premium_gift.confirm_gift(request, request.POST.get('secret'))
            (messages.success if ok else messages.error)(request, msg)
        elif action == 'cancel':
            premium_gift.cancel_gift(request)
            messages.info(request, "Sovğa bekor qilindi.")
        return redirect('coin:gift_premium')

    pending = premium_gift.get_pending(request)
    pending_view = None
    if pending:
        recipient = CustomUser.objects.filter(pk=pending['recipient']).first()
        plans, _ = get_premium_plans_for_user(request.user)
        if recipient:
            pending_view = {'recipient': recipient, 'plan': plans[pending['plan']], 'method': pending['method']}
        else:
            premium_gift.cancel_gift(request)

    plans, _ = get_premium_plans_for_user(request.user)
    return render(request, 'coin/market/gift_premium.html', {
        'plans': plans,
        'eligible': can_user_buy_premium(request.user),
        'pending': pending_view,
        'has_telegram': bool(request.user.telegram_id),
        'has_password': request.user.has_usable_password(),
        'sent_gifts': PremiumRequest.objects.filter(gifted_by=request.user).select_related('user')[:10],
    })


@login_required
def gift_premium_lookup(request):
    """Sovğa sahifasi uçun: ID / login / telefon böyiça öquvçini körsatiş."""
    from django.http import JsonResponse
    from accounts.course_membership import find_student
    from .premium_gift import recipient_problem

    query = (request.GET.get('q') or '').strip().lstrip('@')
    if len(query) < 2:
        return JsonResponse({'found': False})
    recipient = find_student(query)
    if recipient is None:
        return JsonResponse({'found': False, 'error': "Öquvçi topilmadi."})
    problem = recipient_problem(request.user, recipient)
    data = {
        'found': True,
        'ok': problem is None,
        'error': problem or '',
        'full_name': recipient.full_name,
        'username': recipient.username,
        'student_id': recipient.student_id,
        'initials': recipient.get_initials(),
        'photo': recipient.photo.url if recipient.photo else None,
        'is_premium': bool(recipient.is_premium),
        'premium_until': (timezone.localtime(recipient.premium_expires_at).strftime('%d.%m.%Y')
                          if recipient.is_premium and recipient.premium_expires_at else None),
    }
    return JsonResponse(data)


# ============== ADMIN: COIN MARKET ==============

@login_required
def admin_products(request):
    if not request.user.is_admin:
        return redirect('home')
    
    products = Product.objects.all()
    return render(request, 'coin/admin/products.html', {'products': products})


PREMIUM_EARLY_ACCESS_HOURS = 24


def _early_access_until(post):
    """Erta kiriş belgilansa — hamma uçun oçiladigan vaqt (hozir + 24 soat)."""
    if 'early_access' in post:
        return timezone.now() + timedelta(hours=PREMIUM_EARLY_ACCESS_HOURS)
    return None


def _announce_new_product(product):
    text = (
        f"🛍 <b>Yangi mahsulot!</b>\n\n"
        f"📦 <b>{product.name}</b>\n"
        f"🪙 Narxi: <b>{product.coin_price}</b> coin\n"
        f"📊 Omborda: {product.stock} ta\n\n"
        f"📝 {product.description[:200]}{'...' if len(product.description) > 200 else ''}"
    )
    recipients = CustomUser.objects.filter(telegram_id__isnull=False)
    if product.premium_only or product.is_early_access:
        # Hamma hali köra olmaydigan mahsulot haqida faqat Premium a'zolarga aytamiz.
        recipients = recipients.filter(is_premium=True).filter(
            db_models.Q(premium_expires_at__isnull=True) | db_models.Q(premium_expires_at__gt=timezone.now())
        )
        tag = "💎 <b>Faqat Premium uçun</b>" if product.premium_only else (
            f"💎 <b>Premium erta kiriş</b> — boşqalar {PREMIUM_EARLY_ACCESS_HOURS} soatdan keyin köradi")
        personal = f"{tag}\n\n{text}\n\n🛒 Xarid qiliş uçun saytga kiring!"
    else:
        notify_group(text)
        personal = (
            f"🛍 <b>Yangi mahsulot qöşildi!</b>\n\n"
            f"📦 <b>{product.name}</b>\n"
            f"🪙 Narxi: <b>{product.coin_price}</b> coin\n\n"
            f"🛒 Xarid qiliş uçun saytga kiring!"
        )
    for u in recipients:
        notify_user(u.telegram_id, personal)


@login_required
def admin_product_add(request):
    if not request.user.is_admin:
        return redirect('home')
    
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        coin_price = request.POST.get('coin_price')
        stock = request.POST.get('stock', 0)
        image = request.FILES.get('image')
        
        if name and description and coin_price and image:
            product = Product.objects.create(
                name=name,
                description=description,
                coin_price=int(coin_price),
                stock=int(stock),
                image=image,
                premium_only='premium_only' in request.POST,
                public_at=_early_access_until(request.POST),
            )
            _announce_new_product(product)

            messages.success(request, "Mahsulot qöşildi!")
            return redirect('coin:admin_products')
        else:
            messages.error(request, "Barça maydonlarni töldiring!")
    
    return render(request, 'coin/admin/product_form.html', {'title': "Mahsulot qöşiş"})


@login_required
def admin_product_edit(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        product.name = request.POST.get('name')
        product.description = request.POST.get('description')
        product.coin_price = int(request.POST.get('coin_price'))
        product.stock = int(request.POST.get('stock', 0))
        product.is_active = 'is_active' in request.POST
        product.premium_only = 'premium_only' in request.POST
        if not product.is_early_access or 'early_access' not in request.POST:
            product.public_at = _early_access_until(request.POST)

        if request.FILES.get('image'):
            product.image = request.FILES.get('image')
        
        product.save()
        messages.success(request, "Mahsulot yangilandi!")
        return redirect('coin:admin_products')
    
    return render(request, 'coin/admin/product_form.html', {'title': "Mahsulotni tahrirlaş", 'product': product})


@login_required
def admin_product_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        product.delete()
        messages.success(request, "Mahsulot öçirildi!")
        return redirect('coin:admin_products')
    
    return render(request, 'coin/admin/product_delete.html', {'product': product})


@login_required
def admin_purchases(request):
    if not request.user.is_admin:
        return redirect('home')
    
    purchases = ProductPurchase.objects.all().select_related('product', 'user')
    return render(request, 'coin/admin/purchases.html', {'purchases': purchases})


@login_required
def admin_mark_delivered(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    purchase = get_object_or_404(ProductPurchase, pk=pk)
    purchase.is_delivered = True
    purchase.status = 'delivered'
    purchase.save()
    
    # Foydalanuvçiga telegram xabar
    if purchase.user.telegram_id:
        notify_user(
            purchase.user.telegram_id,
            f"📦 <b>Mahsulotingiz yetib keldi!</b>\n\n"
            f"📦 <b>{purchase.product.name}</b>\n"
            f"📋 Buyurtma #{purchase.pk}\n\n"
            f"✅ Mahsulotingiz IT Şaharda sizni kutmoqda! Olib ketişingiz mumkin."
        )
    
    # Guruhga telegram xabar
    notify_group(
        f"📦 <b>Mahsulot yetib keldi!</b>\n\n"
        f"Hurmatli <b>{purchase.user.full_name}</b> öquvçi,\n"
        f"🛍 <b>{purchase.product.name}</b> mahsulotingiz IT Şaharda sizni kutmoqda! ✅"
    )
    
    # Foydalanuvçiga xabar (Message)
    Message.objects.create(
        recipient=purchase.user,
        title=f"📦 Buyurtma #{purchase.pk} yetkazildi",
        content=f"'{purchase.product.name}' mahsuloti yetkazildi! Mahsulotingizni olib ketişingiz mumkin.",
        message_type='system'
    )
    
    messages.success(request, "Yetkazildi deb belgilandi!")
    return redirect('coin:admin_purchases')


@login_required
def admin_cancel_purchase(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    purchase = get_object_or_404(ProductPurchase, pk=pk)
    
    if purchase.status != 'pending' or purchase.is_delivered:
        messages.error(request, "Bu buyurtmani bekor qilib bölmaydi!")
        return redirect('coin:admin_purchases')
    
    if request.method == 'POST':
        with transaction.atomic():
            # Holatni şartli UPDATE bilan band qilamiz — tugma ikki marta
            # bosilsa coin ikki marta qaytarilmasin.
            cancelled = ProductPurchase.objects.filter(
                pk=purchase.pk, status='pending', is_delivered=False
            ).update(status='cancelled', cancelled_at=timezone.now())

            if not cancelled:
                messages.error(request, "Bu buyurtmani bekor qilib bölmaydi!")
                return redirect('coin:admin_purchases')

            purchase.refresh_from_db(fields=['status', 'cancelled_at'])

            CustomUser.objects.filter(pk=purchase.user_id).update(
                coins=db_models.F('coins') + purchase.coins_spent
            )
            purchase.user.refresh_from_db(fields=['coins'])

            Product.objects.filter(pk=purchase.product_id).update(
                stock=db_models.F('stock') + 1
            )
            purchase.product.refresh_from_db(fields=['stock'])
            
            CoinTransaction.objects.create(
                user=purchase.user,
                amount=purchase.coins_spent,
                action='add',
                reason=f"Admin tomonidan buyurtma bekor qilindi: {purchase.product.name} (#{purchase.pk})"
            )
            
            # Foydalanuvçiga telegram xabar
            if purchase.user.telegram_id:
                notify_user(
                    purchase.user.telegram_id,
                    f"❌ <b>Buyurtmangiz bekor qilindi</b>\n\n"
                    f"📦 <b>{purchase.product.name}</b>\n"
                    f"🪙 <b>{purchase.coins_spent}</b> coin balansingizga qaytarildi\n\n"
                    f"📋 Buyurtma #{purchase.pk}"
                )
            
            # Foydalanuvçiga xabar (Message)
            Message.objects.create(
                recipient=purchase.user,
                title=f"❌ Buyurtma #{purchase.pk} bekor qilindi",
                content=f"'{purchase.product.name}' mahsuloti uçun buyurtmangiz admin tomonidan bekor qilindi. {purchase.coins_spent} coin balansingizga qaytarildi.",
                message_type='system'
            )
        
        messages.success(request, f"Buyurtma bekor qilindi. {purchase.coins_spent} coin foydalanuvçiga qaytarildi!")
    
    return redirect('coin:admin_purchases')


# ============== ADMIN: ACTIVITY LOG ==============



# ============== ADMIN: COIN TRANSFERS ==============

@login_required
def admin_transfers(request):
    if not request.user.is_admin:
        return redirect('home')

    # Qaysi köriniş: 'transfers' (coin ötkazmalar) yoki 'games' (coin öyinlar)
    view_type = request.GET.get('view', 'transfers')

    filter_type = request.GET.get('filter', 'all')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    now = timezone.now()

    def apply_date_filter(qs):
        if filter_type == 'today':
            qs = qs.filter(created_at__date=now.date())
        elif filter_type == 'week':
            start_of_week = now - timedelta(days=now.weekday())
            qs = qs.filter(created_at__date__gte=start_of_week.date())
        elif filter_type == 'month':
            qs = qs.filter(created_at__year=now.year, created_at__month=now.month)
        elif filter_type == 'custom':
            if date_from:
                qs = qs.filter(created_at__date__gte=date_from)
            if date_to:
                qs = qs.filter(created_at__date__lte=date_to)
        return qs

    # ===== Coin ötkazmalar =====
    transfers = CoinTransfer.objects.all().select_related('sender', 'receiver')
    transfers = apply_date_filter(transfers)

    total_count = transfers.count()
    success_qs = transfers.filter(status='completed')
    success_count = success_qs.count()
    total_coins = success_qs.aggregate(total=Sum('amount'))['total'] or 0
    total_fees = success_qs.aggregate(total=Sum('fee'))['total'] or 0

    # ===== Coin bilan öynalgan öyinlar (BoardMatch, mode='coin') =====
    from games.models import BoardMatch
    from games.external_api import SERVICE_FEE_PERCENT

    games_qs = (
        BoardMatch.objects
        .filter(mode='coin', wager_coins__gt=0)
        .select_related('white_player', 'black_player', 'game')
    )
    games_qs = apply_date_filter(games_qs)

    games_total_count = games_qs.count()
    games_finished_count = games_qs.filter(status='ended').count()
    # Har bir öyinda jami bank = 2 * wager_coins
    games_total_wager = (games_qs.aggregate(total=Sum('wager_coins'))['total'] or 0) * 2
    # Yutgan öyinlardan uşlangan xizmat haqi (durang/bekorlardan taşqari)
    decided_qs = games_qs.filter(status='ended', winner__in=['white', 'black'])
    games_total_fees = sum(
        ((m.wager_coins * 2) * SERVICE_FEE_PERCENT) // 100
        for m in decided_qs
    )

    if view_type == 'games':
        paginator = Paginator(games_qs.order_by('-created_at'), 30)
        page = request.GET.get('page', 1)
        game_matches = paginator.get_page(page)
        transfers_page = None
    else:
        paginator = Paginator(transfers, 30)
        page = request.GET.get('page', 1)
        transfers_page = paginator.get_page(page)
        game_matches = None

    return render(request, 'coin/admin/transfers.html', {
        'view_type': view_type,
        'transfers': transfers_page,
        'game_matches': game_matches,
        'total_count': total_count,
        'success_count': success_count,
        'total_coins': total_coins,
        'total_fees': total_fees,
        'games_total_count': games_total_count,
        'games_finished_count': games_finished_count,
        'games_total_wager': games_total_wager,
        'games_total_fees': games_total_fees,
        'service_fee_percent': SERVICE_FEE_PERCENT,
        'filter_type': filter_type,
        'date_from': date_from,
        'date_to': date_to,
    })
