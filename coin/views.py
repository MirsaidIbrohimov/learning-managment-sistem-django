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
    """Coin o'tkazma sahifasi — alohida sahifa"""
    return render(request, 'coin/transfer.html')


@login_required
def market_list(request):
    """Market sahifasi — data API orqali yuklanadi"""
    return render(request, 'coin/market/list.html')


@login_required
def market_detail(request, pk):
    """Mahsulot detail sahifasi — data API orqali yuklanadi"""
    return render(request, 'coin/market/detail.html', {'product_id': pk})


@login_required
def my_purchases(request):
    """Mening xaridlarim sahifasi — data API orqali yuklanadi"""
    return render(request, 'coin/market/my_purchases.html')


@login_required
def premium_page(request):
    """Premium sahifasi — data API orqali yuklanadi"""
    return render(request, 'coin/market/premium.html')


# ============== ADMIN: COIN MARKET ==============

@login_required
def admin_products(request):
    if not request.user.is_admin:
        return redirect('home')
    
    products = Product.objects.all()
    return render(request, 'coin/admin/products.html', {'products': products})


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
                image=image
            )

            notify_group(
                f"🛍 <b>Yangi mahsulot!</b>\n\n"
                f"📦 <b>{product.name}</b>\n"
                f"🪙 Narxi: <b>{product.coin_price}</b> coin\n"
                f"📊 Omborda: {product.stock} ta\n\n"
                f"📝 {product.description[:200]}{'...' if len(product.description) > 200 else ''}"
            )

            for u in CustomUser.objects.filter(telegram_id__isnull=False):
                notify_user(
                    u.telegram_id,
                    f"🛍 <b>Yangi mahsulot qo'shildi!</b>\n\n"
                    f"📦 <b>{product.name}</b>\n"
                    f"🪙 Narxi: <b>{product.coin_price}</b> coin\n\n"
                    f"🛒 Xarid qilish uchun saytga kiring!"
                )

            messages.success(request, "Mahsulot qo'shildi!")
            return redirect('coin:admin_products')
        else:
            messages.error(request, "Barcha maydonlarni to'ldiring!")
    
    return render(request, 'coin/admin/product_form.html', {'title': "Mahsulot qo'shish"})


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
        
        if request.FILES.get('image'):
            product.image = request.FILES.get('image')
        
        product.save()
        messages.success(request, "Mahsulot yangilandi!")
        return redirect('coin:admin_products')
    
    return render(request, 'coin/admin/product_form.html', {'title': "Mahsulotni tahrirlash", 'product': product})


@login_required
def admin_product_delete(request, pk):
    if not request.user.is_admin:
        return redirect('home')
    
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        product.delete()
        messages.success(request, "Mahsulot o'chirildi!")
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
    
    # Foydalanuvchiga telegram xabar
    if purchase.user.telegram_id:
        notify_user(
            purchase.user.telegram_id,
            f"📦 <b>Mahsulotingiz yetib keldi!</b>\n\n"
            f"📦 <b>{purchase.product.name}</b>\n"
            f"📋 Buyurtma #{purchase.pk}\n\n"
            f"✅ Mahsulotingiz IT Shaharda sizni kutmoqda! Olib ketishingiz mumkin."
        )
    
    # Guruhga telegram xabar
    notify_group(
        f"📦 <b>Mahsulot yetib keldi!</b>\n\n"
        f"Hurmatli <b>{purchase.user.full_name}</b> o'quvchi,\n"
        f"🛍 <b>{purchase.product.name}</b> mahsulotingiz IT Shaharda sizni kutmoqda! ✅"
    )
    
    # Foydalanuvchiga xabar (Message)
    Message.objects.create(
        recipient=purchase.user,
        title=f"📦 Buyurtma #{purchase.pk} yetkazildi",
        content=f"'{purchase.product.name}' mahsuloti yetkazildi! Mahsulotingizni olib ketishingiz mumkin.",
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
        messages.error(request, "Bu buyurtmani bekor qilib bo'lmaydi!")
        return redirect('coin:admin_purchases')
    
    if request.method == 'POST':
        with transaction.atomic():
            purchase.user.coins += purchase.coins_spent
            purchase.user.save(update_fields=['coins'])
            
            purchase.product.stock += 1
            purchase.product.save()
            
            purchase.status = 'cancelled'
            purchase.cancelled_at = timezone.now()
            purchase.save()
            
            CoinTransaction.objects.create(
                user=purchase.user,
                amount=purchase.coins_spent,
                action='add',
                reason=f"Admin tomonidan buyurtma bekor qilindi: {purchase.product.name} (#{purchase.pk})"
            )
            
            # Foydalanuvchiga telegram xabar
            if purchase.user.telegram_id:
                notify_user(
                    purchase.user.telegram_id,
                    f"❌ <b>Buyurtmangiz bekor qilindi</b>\n\n"
                    f"📦 <b>{purchase.product.name}</b>\n"
                    f"🪙 <b>{purchase.coins_spent}</b> coin balansingizga qaytarildi\n\n"
                    f"📋 Buyurtma #{purchase.pk}"
                )
            
            # Foydalanuvchiga xabar (Message)
            Message.objects.create(
                recipient=purchase.user,
                title=f"❌ Buyurtma #{purchase.pk} bekor qilindi",
                content=f"'{purchase.product.name}' mahsuloti uchun buyurtmangiz admin tomonidan bekor qilindi. {purchase.coins_spent} coin balansingizga qaytarildi.",
                message_type='system'
            )
        
        messages.success(request, f"Buyurtma bekor qilindi. {purchase.coins_spent} coin foydalanuvchiga qaytarildi!")
    
    return redirect('coin:admin_purchases')


# ============== ADMIN: ACTIVITY LOG ==============

@login_required
def admin_activities(request):
    if not request.user.is_admin:
        return redirect('home')
    
    activities = ActivityLog.objects.all().select_related('user')
    
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    action_type = request.GET.get('action_type')
    user_id = request.GET.get('user')
    
    if date_from:
        from datetime import datetime
        date_from = datetime.strptime(date_from, '%Y-%m-%d')
        activities = activities.filter(created_at__date__gte=date_from)
    
    if date_to:
        from datetime import datetime
        date_to = datetime.strptime(date_to, '%Y-%m-%d')
        activities = activities.filter(created_at__date__lte=date_to)
    
    if action_type:
        activities = activities.filter(action_type=action_type)
    
    if user_id:
        activities = activities.filter(user_id=user_id)
    
    users = CustomUser.objects.all()
    action_types = ActivityLog.ACTION_TYPES
    
    return render(request, 'coin/admin/activities.html', {
        'activities': activities[:500],
        'users': users,
        'action_types': action_types,
    })


# ============== ADMIN: COIN TRANSFERS ==============

@login_required
def admin_transfers(request):
    if not request.user.is_admin:
        return redirect('home')
    
    transfers = CoinTransfer.objects.all().select_related('sender', 'receiver')
    
    filter_type = request.GET.get('filter', 'all')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    now = timezone.now()
    
    if filter_type == 'today':
        transfers = transfers.filter(created_at__date=now.date())
    elif filter_type == 'week':
        start_of_week = now - timedelta(days=now.weekday())
        transfers = transfers.filter(created_at__date__gte=start_of_week.date())
    elif filter_type == 'month':
        transfers = transfers.filter(created_at__year=now.year, created_at__month=now.month)
    elif filter_type == 'custom':
        if date_from:
            transfers = transfers.filter(created_at__date__gte=date_from)
        if date_to:
            transfers = transfers.filter(created_at__date__lte=date_to)
    
    total_count = transfers.count()
    success_qs = transfers.filter(status='completed')
    success_count = success_qs.count()
    total_coins = success_qs.aggregate(total=Sum('amount'))['total'] or 0
    total_fees = success_qs.aggregate(total=Sum('fee'))['total'] or 0
    
    paginator = Paginator(transfers, 30)
    page = request.GET.get('page', 1)
    transfers = paginator.get_page(page)
    
    return render(request, 'coin/admin/transfers.html', {
        'transfers': transfers,
        'total_count': total_count,
        'success_count': success_count,
        'total_coins': total_coins,
        'total_fees': total_fees,
        'filter_type': filter_type,
        'date_from': date_from,
        'date_to': date_to,
    })
