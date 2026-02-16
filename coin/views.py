import math
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from accounts.models import CustomUser, PremiumRequest, Message
from .models import (
    Product, ProductLike, ProductComment, ProductPurchase, 
    CoinTransaction, ActivityLog
)

PREMIUM_DISCOUNT = 0.05  # 5% chegirma


def get_discounted_price(product, user):
    if user.is_premium:
        return math.floor(product.coin_price * (1 - PREMIUM_DISCOUNT))
    return product.coin_price

PREMIUM_PLANS = {
    'weekly': {'name': 'Haftalik', 'price': 350, 'days': 7},
    'monthly': {'name': '1 oylik', 'price': 700, 'days': 30},
    'bimonthly': {'name': '2 oylik', 'price': 1000, 'days': 60},
}


# ============== COIN MARKET ==============

@login_required
def market_list(request):
    products = Product.objects.filter(is_active=True)
    
    if request.user.is_premium:
        for p in products:
            p.discounted_price = get_discounted_price(p, request.user)
    
    pending_request = None
    if request.user.is_authenticated:
        pending_request = PremiumRequest.objects.filter(
            user=request.user, status='pending'
        ).first()
    
    return render(request, 'coin/market/list.html', {
        'products': products,
        'premium_plans': PREMIUM_PLANS,
        'pending_request': pending_request,
    })


@login_required
def request_premium(request):
    pending = PremiumRequest.objects.filter(user=request.user, status='pending').first()
    if pending:
        messages.info(request, "Sizda allaqachon kutilayotgan Premium so'rov bor!")
        return redirect('coin:market_list')

    if request.method == 'POST':
        plan = request.POST.get('plan')
        if plan not in PREMIUM_PLANS:
            messages.error(request, "Noto'g'ri tarif tanlandi!")
            return redirect('coin:buy_premium')
        
        plan_info = PREMIUM_PLANS[plan]
        price = plan_info['price']
        
        if request.user.coins < price:
            messages.error(request, f"Coinlaringiz yetarli emas! {plan_info['name']} Premium narxi: {price} coin")
            return redirect('coin:buy_premium')
        
        with transaction.atomic():
            request.user.coins -= price
            request.user.save(update_fields=['coins'])
            
            is_ext = request.user.is_premium and request.user.premium_expires_at and request.user.premium_expires_at > timezone.now()
            
            PremiumRequest.objects.create(
                user=request.user,
                plan=plan,
                is_extension=is_ext,
            )
            
            CoinTransaction.objects.create(
                user=request.user,
                amount=price,
                action='remove',
                reason=f"✅ Premium so'rov ({plan_info['name']}) - {price} coin"
            )
            
            ActivityLog.objects.create(
                user=request.user,
                action_type='purchase_product',
                description=f"Premium so'rov yuborildi: {plan_info['name']} ({price} coin)"
            )
            
            admins = CustomUser.objects.filter(role='admin')
            for admin in admins:
                Message.objects.create(
                    sender=request.user,
                    recipient=admin,
                    title="Yangi Premium so'rov ✅",
                    content=f"{request.user.full_name} {plan_info['name']} Premium ({price} coin) uchun so'rov yubordi. Dashboard > Premium boshqaruv bo'limidan tasdiqlang.",
                    message_type='system'
                )
        
        label = "uzaytirish" if is_ext else ""
        messages.success(request, f"Premium {label} so'rovingiz yuborildi! Admin tasdiqlashini kuting.")
        return redirect('coin:market_list')
    
    return render(request, 'coin/market/buy_premium.html', {
        'premium_plans': PREMIUM_PLANS,
        'user': request.user,
    })


@login_required
def extend_premium(request):
    if not request.user.is_premium:
        messages.error(request, "Siz hali Premium foydalanuvchi emassiz!")
        return redirect('coin:market_list')
    
    pending = PremiumRequest.objects.filter(user=request.user, status='pending').first()
    if pending:
        messages.info(request, "Sizda allaqachon kutilayotgan Premium so'rov bor!")
        return redirect('coin:market_list')
    
    if request.method == 'POST':
        plan = request.POST.get('plan')
        if plan not in PREMIUM_PLANS:
            messages.error(request, "Noto'g'ri tarif tanlandi!")
            return redirect('coin:extend_premium')
        
        plan_info = PREMIUM_PLANS[plan]
        price = plan_info['price']
        
        if request.user.coins < price:
            messages.error(request, f"Coinlaringiz yetarli emas! {plan_info['name']} Premium narxi: {price} coin")
            return redirect('coin:extend_premium')
        
        with transaction.atomic():
            request.user.coins -= price
            request.user.save(update_fields=['coins'])
            
            PremiumRequest.objects.create(
                user=request.user,
                plan=plan,
                is_extension=True,
            )
            
            CoinTransaction.objects.create(
                user=request.user,
                amount=price,
                action='remove',
                reason=f"✅ Premium uzaytirish so'rovi ({plan_info['name']}) - {price} coin"
            )
            
            ActivityLog.objects.create(
                user=request.user,
                action_type='purchase_product',
                description=f"Premium uzaytirish so'rovi: {plan_info['name']} ({price} coin)"
            )
            
            admins = CustomUser.objects.filter(role='admin')
            for admin in admins:
                Message.objects.create(
                    sender=request.user,
                    recipient=admin,
                    title="Premium uzaytirish so'rovi ✅",
                    content=f"{request.user.full_name} Premium muddatini {plan_info['name']} ga uzaytirish uchun so'rov yubordi ({price} coin). Dashboard > Premium boshqaruv bo'limidan tasdiqlang.",
                    message_type='system'
                )
        
        messages.success(request, "Premium uzaytirish so'rovingiz yuborildi! Admin tasdiqlashini kuting.")
        return redirect('coin:market_list')
    
    return render(request, 'coin/market/extend_premium.html', {
        'premium_plans': PREMIUM_PLANS,
        'user': request.user,
    })


@login_required
def market_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    comments = product.comments.all()
    is_liked = product.likes.filter(user=request.user).exists()
    can_purchase = request.user.coins >= product.coin_price and product.stock > 0
    
    if request.method == 'POST' and 'comment' in request.POST:
        content = request.POST.get('content')
        if content:
            from datetime import timedelta
            one_hour_ago = timezone.now() - timedelta(hours=1)
            recent_comment = ProductComment.objects.filter(
                user=request.user,
                created_at__gte=one_hour_ago
            ).exists()
            
            if recent_comment:
                messages.error(request, "Siz 1 soatda faqat bitta izoh qoldirishingiz mumkin! ⏰")
                return redirect('coin:market_detail', pk=pk)
            
            ProductComment.objects.create(
                product=product,
                user=request.user,
                content=content
            )
            if request.user.is_premium:
                request.user.add_coins(1, f"Mahsulotga izoh (Premium): {product.name}")
                messages.success(request, "Izoh qo'shildi (+1 coin Premium bonus)! ✨")
            else:
                request.user.remove_coins(1, f"Mahsulotga izoh yozish: {product.name}")
                messages.success(request, "Izoh qo'shildi (-1 coin)")
            ActivityLog.objects.create(
                user=request.user,
                action_type='comment_product',
                description=f"Mahsulotga izoh qoldirdi: {product.name}"
            )
            return redirect('coin:market_detail', pk=pk)
    
    discounted_price = get_discounted_price(product, request.user)
    has_discount = request.user.is_premium and discounted_price < product.coin_price
    can_purchase = request.user.coins >= discounted_price and product.stock > 0
    
    return render(request, 'coin/market/detail.html', {
        'product': product,
        'comments': comments,
        'is_liked': is_liked,
        'can_purchase': can_purchase,
        'discounted_price': discounted_price,
        'has_discount': has_discount,
    })


@login_required
def market_like(request, pk):
    product = get_object_or_404(Product, pk=pk)
    like = ProductLike.objects.filter(product=product, user=request.user).first()
    
    if like:
        coin_back = 2 if request.user.is_premium else 1
        if like.coin_awarded:
            request.user.remove_coins(coin_back, f"Mahsulotga like bekor qilindi: {product.name}")
        like.delete()
    else:
        coin_amount = 2 if request.user.is_premium else 1
        like = ProductLike.objects.create(product=product, user=request.user)
        request.user.add_coins(coin_amount, f"Mahsulotga like: {product.name}")
        like.coin_awarded = True
        like.save()
        ActivityLog.objects.create(
            user=request.user,
            action_type='like_product',
            description=f"Mahsulotga like bosdi: {product.name} (+{coin_amount} coin)"
        )
    
    return redirect('coin:market_detail', pk=pk)


@login_required
def market_purchase(request, pk):
    product = get_object_or_404(Product, pk=pk)
    final_price = get_discounted_price(product, request.user)
    has_discount = request.user.is_premium and final_price < product.coin_price
    
    if request.user.coins < final_price:
        messages.error(request, "Coinlaringiz yetarli emas!")
        return redirect('coin:market_detail', pk=pk)
    
    if product.stock <= 0:
        messages.error(request, "Mahsulot tugagan!")
        return redirect('coin:market_detail', pk=pk)
    
    if request.method == 'POST':
        request.user.coins -= final_price
        request.user.save()
        
        product.stock -= 1
        product.save()
        
        ProductPurchase.objects.create(
            product=product,
            user=request.user,
            coins_spent=final_price
        )
        
        discount_label = " (Premium -5%)" if has_discount else ""
        CoinTransaction.objects.create(
            user=request.user,
            amount=final_price,
            action='remove',
            reason=f"Mahsulot sotib olindi: {product.name}{discount_label}"
        )
        ActivityLog.objects.create(
            user=request.user,
            action_type='purchase_product',
            description=f"Mahsulot sotib oldi: {product.name} ({final_price} coin{discount_label})"
        )
        
        messages.success(request, f"'{product.name}' muvaffaqiyatli sotib olindi!")
        return redirect('coin:market_list')
    
    return render(request, 'coin/market/purchase_confirm.html', {
        'product': product,
        'final_price': final_price,
        'has_discount': has_discount,
    })


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
            Product.objects.create(
                name=name,
                description=description,
                coin_price=int(coin_price),
                stock=int(stock),
                image=image
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
    purchase.save()
    messages.success(request, "Yetkazildi deb belgilandi!")
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
