import logging
import math
import secrets
import string
from datetime import timedelta

api_audit = logging.getLogger('api.audit')

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import F, Sum, Q
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from api.permissions import CoinTransferRateThrottle, IsNotBlocked
from coin.models import Product, ProductLike, ProductComment, ProductPurchase, CoinTransaction, ActivityLog, CoinTransfer
from coin.pricing import get_product_price
from accounts.models import CustomUser, PremiumRequest, Message
from telegram_bot.utils import notify_group, notify_user, notify_admins
from .serializers import (
    ProductSerializer, ProductCommentSerializer, ProductPurchaseSerializer,
    CoinTransactionSerializer, ActivityLogSerializer, CoinSummarySerializer,
    ProductCommentCreateSerializer, PremiumRequestSerializer,
    CoinTransferSearchResultSerializer, CoinTransferInitSerializer,
    CoinTransferConfirmSerializer, CoinTransferDetailSerializer,
)

PREMIUM_PLANS_BASE = {
    'weekly': {'name': 'Haftalik', 'days': 7, 'percent': 25, 'min_price': 500},
    'monthly': {'name': '1 oylik', 'days': 30, 'percent': 50, 'min_price': 750},
    'bimonthly': {'name': '2 oylik', 'days': 60, 'percent': 75, 'min_price': 1000},
}


def get_premium_plans_for_user(user):
    """Foydalanuvçiga mos premium narxlarni hisoblaş (hozirgi balansga qarab)"""
    total_earned = user.coins
    plans = {}
    for key, base in PREMIUM_PLANS_BASE.items():
        price = math.floor(total_earned * base['percent'] / 100)
        too_cheap = price < base['min_price']
        plans[key] = {
            'name': base['name'],
            'price': price,
            'days': base['days'],
            'percent': base['percent'],
            'min_price': base['min_price'],
            'too_cheap': too_cheap,
        }
    return plans, total_earned


def can_user_buy_premium(user):
    """Foydalanuvçi kamida 1 oy oldin röyxatdan ötganmi"""
    if not user.date_joined:
        return False
    return (timezone.now() - user.date_joined).days >= 30


class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, IsNotBlocked]

    def get_queryset(self):
        qs = Product.objects.filter(is_active=True).order_by('-created_at')
        search = self.request.query_params.get('search', '')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return qs


class ProductDetailView(generics.RetrieveAPIView):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, IsNotBlocked]
    queryset = Product.objects.filter(is_active=True)


class ProductCommentsView(generics.ListAPIView):
    serializer_class = ProductCommentSerializer
    permission_classes = [IsAuthenticated, IsNotBlocked]

    def get_queryset(self):
        return ProductComment.objects.filter(product_id=self.kwargs['pk']).select_related('user')


class MyPurchasesView(generics.ListAPIView):
    serializer_class = ProductPurchaseSerializer
    permission_classes = [IsAuthenticated, IsNotBlocked]

    def get_queryset(self):
        qs = ProductPurchase.objects.filter(user=self.request.user).select_related('product')
        status_filter = self.request.query_params.get('status', '')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class CoinTransactionListView(generics.ListAPIView):
    serializer_class = CoinTransactionSerializer
    permission_classes = [IsAuthenticated, IsNotBlocked]

    def get_queryset(self):
        qs = CoinTransaction.objects.filter(user=self.request.user)
        action = self.request.query_params.get('action', '')
        if action:
            qs = qs.filter(action=action)
        search = self.request.query_params.get('search', '')
        if search:
            qs = qs.filter(reason__icontains=search)
        date_from = self.request.query_params.get('date_from', '')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = self.request.query_params.get('date_to', '')
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs


class ActivityLogListView(generics.ListAPIView):
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated, IsNotBlocked]

    def get_queryset(self):
        qs = ActivityLog.objects.filter(user=self.request.user)
        action_type = self.request.query_params.get('action_type', '')
        if action_type:
            qs = qs.filter(action_type=action_type)
        return qs


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def coin_summary(request):
    user = request.user
    transactions = CoinTransaction.objects.filter(user=user)
    total_earned = transactions.filter(action='add').aggregate(total=Sum('amount'))['total'] or 0
    total_spent = transactions.filter(action__in=['remove', 'purchase']).aggregate(total=Sum('amount'))['total'] or 0
    data = {
        'total_coins': user.coins,
        'total_earned': total_earned,
        'total_spent': total_spent,
        'total_transactions': transactions.count(),
        'is_premium': user.is_premium,
    }
    serializer = CoinSummarySerializer(data)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def market_stats(request):
    """Marketing UI uçun umumiy statistika: social proof, urgency taymer, trending mahsulotlar."""
    from django.db.models import Count

    now = timezone.now()
    today = now.date()

    weekday = now.weekday()
    days_ahead = (6 - weekday) % 7
    if days_ahead == 0 and now.hour >= 20:
        days_ahead = 7
    week_ends_at = (now + timedelta(days=days_ahead)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )

    top_product_ids = list(
        ProductPurchase.objects.filter(status__in=['pending', 'delivered'])
        .values('product_id')
        .annotate(c=Count('id'))
        .order_by('-c')[:3]
        .values_list('product_id', flat=True)
    )

    return Response({
        'active_premium_users': CustomUser.objects.filter(
            is_premium=True, premium_expires_at__gt=now
        ).count(),
        'total_purchases': ProductPurchase.objects.filter(
            status__in=['pending', 'delivered']
        ).count(),
        'purchases_today': ProductPurchase.objects.filter(
            status__in=['pending', 'delivered'], purchased_at__date=today
        ).count(),
        'total_users': CustomUser.objects.filter(is_active=True).count(),
        'top_product_ids': top_product_ids,
        'week_ends_at': week_ends_at.isoformat(),
        'server_now': now.isoformat(),
    })


# ============== WRITE ENDPOINTS ==============


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def toggle_like(request, pk):
    product = get_object_or_404(Product, pk=pk)
    like = ProductLike.objects.filter(product=product, user=request.user).first()

    if like:
        coin_back = 2 if request.user.is_premium else 1
        if like.coin_awarded:
            request.user.remove_coins(coin_back, f"Mahsulotga like bekor qilindi: {product.name}")
        like.delete()
        return Response({'liked': False, 'likes_count': product.likes_count})
    else:
        coin_amount = 2 if request.user.is_premium else 1
        like = ProductLike.objects.create(product=product, user=request.user, coin_awarded=True)
        request.user.add_coins(coin_amount, f"Mahsulotga like: {product.name}")
        ActivityLog.objects.create(
            user=request.user,
            action_type='like_product',
            description=f"Mahsulotga like bosdi: {product.name} (+{coin_amount} coin)"
        )
        return Response({'liked': True, 'likes_count': product.likes_count}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def purchase_product(request, pk):
    # Kursni tugatgan (muzlatilgan) öquvçilar magazindan xarid qila olmaydi
    if request.user.is_finished:
        return Response(
            {'error': "Hisobingiz muzlatilgan. Kursni tugatgan öquvçilar magazindan xarid qila olmaydi."},
            status=status.HTTP_403_FORBIDDEN
        )
    product = get_object_or_404(Product, pk=pk)
    final_price = get_product_price(product, request.user)
    has_discount = request.user.is_premium and final_price < product.coin_price

    # Balans va zaxira TEKŞIRUVI yeçiş bilan bir atomic blokda bölişi
    # şart. Ilgari tekşiruv blokdan taşqarida edi: parallel ikki sörov bir
    # xil balansni körib ikkisi ham ötib ketardi (double-spend) va zaxira
    # manfiyga tuşardi (oversell).
    with transaction.atomic():
        stock_taken = Product.objects.filter(pk=product.pk, stock__gt=0).update(
            stock=F('stock') - 1
        )
        if not stock_taken:
            return Response({'error': "Mahsulot tugagan!"}, status=status.HTTP_400_BAD_REQUEST)

        discount_label = " (Premium -5%)" if has_discount else ""
        if not request.user.try_spend_coins(
            final_price, f"Mahsulot sotib olindi: {product.name}{discount_label}"
        ):
            # Zaxirani qaytarib qöyamiz — pul yeçilmadi, tovar band bölmasin.
            Product.objects.filter(pk=product.pk).update(stock=F('stock') + 1)
            return Response({'error': "Coinlaringiz yetarli emas!"}, status=status.HTTP_400_BAD_REQUEST)

        product.refresh_from_db(fields=['stock'])

        purchase = ProductPurchase.objects.create(
            product=product,
            user=request.user,
            coins_spent=final_price
        )

        ActivityLog.objects.create(
            user=request.user,
            action_type='purchase_product',
            description=f"Mahsulot sotib oldi: {product.name} ({final_price} coin{discount_label})"
        )

        notify_admins(
            f"🛒 <b>Yangi buyurtma!</b>\n\n"
            f"👤 <b>{request.user.full_name}</b> (@{request.user.username})\n"
            f"📦 Mahsulot: <b>{product.name}</b>\n"
            f"🪙 Narxi: <b>{final_price}</b> coin{discount_label}\n"
            f"📊 Qolgan: {product.stock} ta\n\n"
            f"📋 Buyurtma #{purchase.pk}"
        )

        if request.user.telegram_id:
            notify_user(
                request.user.telegram_id,
                f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
                f"📦 <b>{product.name}</b>\n"
                f"🪙 Narxi: <b>{final_price}</b> coin\n\n"
                f"📋 Buyurtma #{purchase.pk}\n"
                f"⏳ Holat: Kutilmoqda\n\n"
                f"❌ Bekor qiliş uçun saytga kiring."
            )

        Message.objects.create(
            recipient=request.user,
            title=f"✅ Buyurtma #{purchase.pk} qabul qilindi",
            content=f"Siz '{product.name}' mahsulotini {final_price} coin ga sotib oldingiz. Buyurtmangiz kutilmoqda. Agar bekor qilmoqçi bölsangiz, 'Mening xaridlarim' bölimiga öting.",
            message_type='system'
        )

    api_audit.info(
        f"Product purchased: user={request.user.username}, product={product.name}, "
        f"price={final_price}, user_id={request.user.pk}"
    )
    serializer = ProductPurchaseSerializer(purchase)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def cancel_purchase(request, pk):
    purchase = get_object_or_404(ProductPurchase, pk=pk, user=request.user)

    if not purchase.can_cancel:
        return Response({'error': "Bu buyurtmani bekor qilib bölmaydi!"}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        # Holatni şartli UPDATE bilan özgartiramiz: agar buyurtma allaqaçon
        # bekor qilingan bölsa 0 satr yangilanadi va biz çiqib ketamiz.
        # Ilgari holat blokdan taşqarida tekşirilardi — bir vaqtda yuborilgan
        # ikki "bekor qiliş" sörovi coinni ikki marta qaytarardi.
        cancelled = ProductPurchase.objects.filter(
            pk=purchase.pk, status='pending', is_delivered=False
        ).update(status='cancelled', cancelled_at=timezone.now())

        if not cancelled:
            return Response(
                {'error': "Bu buyurtmani bekor qilib bölmaydi!"},
                status=status.HTTP_400_BAD_REQUEST
            )

        purchase.refresh_from_db(fields=['status', 'cancelled_at'])

        # Coin qaytariş — `add_coins` emas, chunki u muzlatilgan hisoblarni
        # ötkazib yuboradi, pul qaytariş esa har holatda bajarilişi kerak.
        CustomUser.objects.filter(pk=purchase.user_id).update(
            coins=F('coins') + purchase.coins_spent
        )
        purchase.user.refresh_from_db(fields=['coins'])

        Product.objects.filter(pk=purchase.product_id).update(stock=F('stock') + 1)
        purchase.product.refresh_from_db(fields=['stock'])

        CoinTransaction.objects.create(
            user=purchase.user,
            amount=purchase.coins_spent,
            action='add',
            reason=f"Buyurtma bekor qilindi: {purchase.product.name} (#{purchase.pk})"
        )

        ActivityLog.objects.create(
            user=purchase.user,
            action_type='purchase_product',
            description=f"Buyurtma bekor qildi: {purchase.product.name} (+{purchase.coins_spent} coin qaytarildi)"
        )

        notify_admins(
            f"❌ <b>Buyurtma bekor qilindi!</b>\n\n"
            f"👤 <b>{purchase.user.full_name}</b> (@{purchase.user.username})\n"
            f"📦 Mahsulot: <b>{purchase.product.name}</b>\n"
            f"🪙 Qaytarildi: <b>{purchase.coins_spent}</b> coin\n\n"
            f"📋 Buyurtma #{purchase.pk}"
        )

        if purchase.user.telegram_id:
            notify_user(
                purchase.user.telegram_id,
                f"❌ <b>Buyurtmangiz bekor qilindi</b>\n\n"
                f"📦 <b>{purchase.product.name}</b>\n"
                f"🪙 <b>{purchase.coins_spent}</b> coin balansingizga qaytarildi\n\n"
                f"📋 Buyurtma #{purchase.pk}"
            )

        Message.objects.create(
            recipient=purchase.user,
            title=f"❌ Buyurtma #{purchase.pk} bekor qilindi",
            content=f"'{purchase.product.name}' mahsuloti uçun buyurtmangiz bekor qilindi. {purchase.coins_spent} coin balansingizga qaytarildi.",
            message_type='system'
        )

    serializer = ProductPurchaseSerializer(purchase)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def add_comment(request, pk):
    product = get_object_or_404(Product, pk=pk)
    serializer = ProductCommentCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    one_hour_ago = timezone.now() - timedelta(hours=1)
    recent_comment = ProductComment.objects.filter(
        user=request.user,
        created_at__gte=one_hour_ago
    ).exists()

    if recent_comment:
        return Response(
            {'error': "Siz 1 soatda faqat bitta izoh qoldirişingiz mumkin! ⏰"},
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )

    comment = ProductComment.objects.create(
        product=product,
        user=request.user,
        content=serializer.validated_data['content']
    )

    if request.user.is_premium:
        request.user.add_coins(1, f"Mahsulotga izoh (Premium): {product.name}")
    else:
        request.user.remove_coins(1, f"Mahsulotga izoh yoziş: {product.name}")

    ActivityLog.objects.create(
        user=request.user,
        action_type='comment_product',
        description=f"Mahsulotga izoh qoldirdi: {product.name}"
    )

    return Response(ProductCommentSerializer(comment).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def request_premium(request):
    # Kursni tugatgan (muzlatilgan) öquvçilar coin sarflay olmaydi
    if request.user.is_finished:
        return Response(
            {'error': "Hisobingiz muzlatilgan. Kursni tugatgan öquvçilar coin sarflay olmaydi."},
            status=status.HTTP_403_FORBIDDEN
        )
    serializer = PremiumRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    plan = serializer.validated_data['plan']

    if not can_user_buy_premium(request.user):
        return Response(
            {'error': "Premium sotib oliş uçun kamida 1 oy oldin röyxatdan ötgan bölişingiz kerak!"},
            status=status.HTTP_400_BAD_REQUEST
        )

    pending = PremiumRequest.objects.filter(user=request.user, status='pending').first()
    if pending:
        return Response(
            {'error': "Sizda allaqaçon kutilayotgan Premium sörov bor!"},
            status=status.HTTP_400_BAD_REQUEST
        )

    plans, total_earned = get_premium_plans_for_user(request.user)
    plan_info = plans[plan]
    price = plan_info['price']

    if plan_info['too_cheap']:
        return Response(
            {'error': f"Narx juda arzon! {plan_info['name']} uçun kamida {plan_info['min_price']} coin kerak. Coinlar yiğişni davom eting!"},
            status=status.HTTP_400_BAD_REQUEST
        )

    with transaction.atomic():
        # Kutilayotgan sörovni atomic blok IÇIDA yana bir marta tekşiramiz:
        # aks holda bir vaqtda kelgan ikki sörov ikki marta coin yeçardi.
        if PremiumRequest.objects.filter(user=request.user, status='pending').exists():
            return Response(
                {'error': "Sizda allaqaçon kutilayotgan Premium sörov bor!"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not request.user.try_spend_coins(
            price, f"✅ Premium sörov ({plan_info['name']}) - {price} coin"
        ):
            return Response(
                {'error': f"Coinlaringiz yetarli emas! {plan_info['name']} Premium narxi: {price} coin"},
                status=status.HTTP_400_BAD_REQUEST
            )

        is_ext = (
            request.user.is_premium
            and request.user.premium_expires_at
            and request.user.premium_expires_at > timezone.now()
        )

        PremiumRequest.objects.create(
            user=request.user,
            plan=plan,
            coins_paid=price,
            is_extension=is_ext,
        )

        ActivityLog.objects.create(
            user=request.user,
            action_type='purchase_product',
            description=f"Premium sörov yuborildi: {plan_info['name']} ({price} coin)"
        )

        admins = CustomUser.objects.filter(role='admin')
        for admin in admins:
            Message.objects.create(
                sender=request.user,
                recipient=admin,
                title="Yangi Premium sörov ✅",
                content=f"{request.user.full_name} {plan_info['name']} Premium ({price} coin) uçun sörov yubordi. Dashboard > Premium boşqaruv bölimidan tasdiqlang.",
                message_type='system'
            )

    label = "uzaytiriş " if is_ext else ""
    return Response(
        {'message': f"Premium {label}sörovingiz yuborildi! Admin tasdiqlaşini kuting."},
        status=status.HTTP_201_CREATED
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def premium_plans(request):
    pending = PremiumRequest.objects.filter(user=request.user, status='pending').first()
    user = request.user
    plans, total_earned = get_premium_plans_for_user(user)
    eligible = can_user_buy_premium(user)

    days_since_reg = (timezone.now() - user.date_joined).days if user.date_joined else 0
    days_until_eligible = max(0, 30 - days_since_reg)

    data = {
        'plans': plans,
        'total_earned': total_earned,
        'has_pending_request': pending is not None,
        'is_premium': user.is_premium,
        'premium_expires_at': user.premium_expires_at.isoformat() if user.premium_expires_at else None,
        'premium_purchased_at': user.premium_purchased_at.isoformat() if user.premium_purchased_at else None,
        'eligible': eligible,
        'days_until_eligible': days_until_eligible,
    }

    if pending:
        data['pending_request'] = {
            'id': pending.id,
            'plan': pending.plan,
            'plan_display': pending.get_plan_display(),
            'price': pending.price,
            'created_at': pending.created_at.isoformat(),
        }

    # Oxirgi 5 ta premium sörovlar tarixi
    history = PremiumRequest.objects.filter(user=user).order_by('-created_at')[:5]
    data['request_history'] = [
        {
            'id': r.id,
            'plan': r.plan,
            'plan_display': r.get_plan_display(),
            'status': r.status,
            'status_display': r.get_status_display(),
            'price': r.price,
            'is_extension': r.is_extension,
            'created_at': r.created_at.isoformat(),
            'reviewed_at': r.reviewed_at.isoformat() if r.reviewed_at else None,
        }
        for r in history
    ]

    return Response(data)


# ============== COIN TRANSFER ==============


def _clean_transfer_username(value):
    """Frontend/user kiritmasidan kelgan username'ni normal holatga keltiriş."""
    return (value or '').strip().lstrip('@').strip()


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def search_user_for_transfer(request):
    """Username yoki telefon raqam böyiça foydalanuvçi qidiriş"""
    raw_query = request.query_params.get('username', '').strip()
    query = _clean_transfer_username(raw_query)
    if not query or len(query) < 2:
        return Response({'error': "Kamida 2 ta belgi kiriting"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Kursni tugatgan (muzlatilgan) öquvçilarga coin ötkazib bölmaydi —
    # ularning coinlari köpaymasligi kerak
    base_qs = CustomUser.objects.filter(
        is_blocked=False, is_finished=False,
    ).exclude(pk=request.user.pk)
    
    # Telefon raqam böyiça qidiriş (raqam bilan boşlansa)
    phone_digits = ''.join(ch for ch in raw_query if ch.isdigit())
    if phone_digits and len(phone_digits) >= 2:
        phone_q = Q(phone__icontains=phone_digits)
        if phone_digits.startswith('998') and len(phone_digits) == 12:
            phone_q |= Q(phone__icontains=phone_digits[3:])
        users = base_qs.filter(phone_q)[:5]
    else:
        # Username yoki ism böyiça qidiriş
        users = base_qs.filter(
            Q(username__icontains=query) |
            Q(telegram_username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )[:5]
    
    serializer = CoinTransferSearchResultSerializer(users, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsNotBlocked])
@throttle_classes([CoinTransferRateThrottle])
def initiate_transfer(request):
    """Coin ötkazmani boşlaş — tasdiqlaş kodi yuboriş"""
    # Kursni tugatgan (muzlatilgan) öquvçilar coin ötkaza olmaydi
    if request.user.is_finished:
        return Response(
            {'error': "Hisobingiz muzlatilgan. Kursni tugatgan öquvçilar coin ötkaza olmaydi."},
            status=status.HTTP_403_FORBIDDEN
        )
    serializer = CoinTransferInitSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    receiver_username = _clean_transfer_username(serializer.validated_data['receiver_username'])
    amount = serializer.validated_data['amount']
    
    # Qabul qiluvçini topiş
    receiver = CustomUser.objects.filter(username__iexact=receiver_username, is_blocked=False).first()
    if not receiver:
        return Response({'error': "Foydalanuvçi topilmadi!"}, status=status.HTTP_404_NOT_FOUND)
    
    if receiver.pk == request.user.pk:
        return Response({'error': "Özingizga coin ötkaza olmaysiz!"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Qabul qiluvçi kursni tugatgan (muzlatilgan) bölsa — coin ötkazib bölmaydi
    if getattr(receiver, 'is_finished', False):
        return Response(
            {'error': "Bu foydalanuvçi hisobi muzlatilgan, unga coin ötkazib bölmaydi."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # 10% xizmat haqqi
    fee = math.ceil(amount * 0.10)
    total_deducted = amount + fee
    
    if request.user.coins < total_deducted:
        return Response({
            'error': f"Coinlaringiz yetarli emas! Kerak: {total_deducted} coin ({amount} + {fee} xizmat haqqi), Balansingiz: {request.user.coins}"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Kutilayotgan ötkazma bor-yöqligini tekşiriş
    pending = CoinTransfer.objects.filter(sender=request.user, status='pending').first()
    if pending:
        # Eskisini bekor qiliş
        pending.status = 'cancelled'
        pending.save()
    
    # Tasdiqlaş kodi — pul harakatini himoyalaydi, şuning uçun `secrets`.
    code = ''.join(secrets.choice(string.digits) for _ in range(6))
    
    transfer = CoinTransfer.objects.create(
        sender=request.user,
        receiver=receiver,
        amount=amount,
        fee=fee,
        total_deducted=total_deducted,
        verification_code=code,
        status='pending',
    )
    
    api_audit.info(
        f"Coin transfer initiated: sender={request.user.username}, "
        f"receiver={receiver.username}, amount={amount}, fee={fee}, transfer_id={transfer.pk}"
    )
    # Agar telegram ulangan bölsa — kodni telegramga yuboriş
    needs_telegram = bool(request.user.telegram_id)
    if needs_telegram:
        notify_user(
            request.user.telegram_id,
            f"🔐 <b>Coin ötkazma tasdiqlaş kodi</b>\n\n"
            f"👤 Qabul qiluvçi: <b>{receiver.full_name}</b> (@{receiver.username})\n"
            f"🪙 Miqdor: <b>{amount}</b> coin\n"
            f"💰 Xizmat haqqi: <b>{fee}</b> coin\n"
            f"📊 Jami: <b>{total_deducted}</b> coin\n\n"
            f"🔑 Tasdiqlaş kodi: <b>{code}</b>\n\n"
            f"⏱ Kod 2 daqiqa amal qiladi!\n"
            f"⚠️ Bu kodni heç kimga bermang!"
        )
    
    data = CoinTransferDetailSerializer(transfer).data
    data['needs_telegram_code'] = needs_telegram
    return Response(data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsNotBlocked])
@throttle_classes([CoinTransferRateThrottle])
def confirm_transfer(request):
    """Coin ötkazmani tasdiqlaş"""
    # Muzlatilgan hisob `initiate_transfer` da ham tösiladi — bu yerda ham
    # tekşiramiz, chunki holat ikki sörov orasida özgargan bölişi mumkin.
    if request.user.is_finished:
        return Response(
            {'error': "Hisobingiz muzlatilgan. Kursni tugatgan öquvçilar coin ötkaza olmaydi."},
            status=status.HTTP_403_FORBIDDEN
        )
    serializer = CoinTransferConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    transfer_id = serializer.validated_data['transfer_id']
    
    # Tasdiqlaş kodini SOLIŞTIRIŞ va ötkazmani BAJARIŞ bitta atomic
    # blokda, ötkazma satri qulflangan holda bölişi şart. Ilgari tekşiruv
    # blokdan taşqarida edi: bir xil kod bilan parallel yuborilgan ikki sörov
    # ikkisi ham ötib ketib, qabul qiluvçiga ikki barobar coin tuşardi.
    with transaction.atomic():
        transfer = (
            CoinTransfer.objects.select_for_update()
            .filter(pk=transfer_id, sender=request.user, status='pending')
            .first()
        )
        if transfer is None:
            return Response(
                {'error': "Ötkazma topilmadi yoki muddati ötgan!"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Muddatni tekşiriş (2 daqiqa)
        if (timezone.now() - transfer.created_at).total_seconds() > 120:
            transfer.status = 'cancelled'
            transfer.save(update_fields=['status'])
            return Response(
                {'error': "Ötkazma muddati ötdi! Qaytadan urinib köring."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Tasdiqlaş: telegram kodi yoki parol
        needs_telegram = bool(request.user.telegram_id)

        if needs_telegram:
            # `compare_digest` — kodni bayt-bayt soliştirişda vaqt böyiça
            # sizib çiqişni (timing leak) yopadi. `isdigit()` tekşiruvi
            # ASCII bölmagan kirişda TypeError bölmasligi uçun.
            code = str(serializer.validated_data.get('code', '') or '').strip()
            if not code.isdigit() or not secrets.compare_digest(code, transfer.verification_code):
                return Response({'error': "Tasdiqlaş kodi notöğri!"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            password = serializer.validated_data.get('password', '')
            if not password or not request.user.check_password(password):
                return Response({'error': "Parol notöğri!"}, status=status.HTTP_400_BAD_REQUEST)

        # Holatni şartli UPDATE bilan band qilamiz — ötkazma faqat bir marta
        # 'completed' ga ötişi kafolatlanadi.
        claimed = CoinTransfer.objects.filter(pk=transfer.pk, status='pending').update(
            status='completed', completed_at=timezone.now()
        )
        if not claimed:
            return Response(
                {'error': "Ötkazma allaqaçon bajarilgan!"},
                status=status.HTTP_400_BAD_REQUEST
            )
        transfer.refresh_from_db(fields=['status', 'completed_at'])

        # Yuboruvçidan yeçiş — balans yetarli bölmasa heç narsa yeçilmaydi.
        if not request.user.try_spend_coins(
            transfer.total_deducted,
            f"Coin ötkazma: {transfer.receiver.full_name} ga {transfer.amount} coin "
            f"({transfer.fee} xizmat haqqi)",
        ):
            transaction.set_rollback(True)
            return Response({'error': "Coinlaringiz yetarli emas!"}, status=status.HTTP_400_BAD_REQUEST)

        # Qabul qiluvçiga qöşiş
        CustomUser.objects.filter(pk=transfer.receiver_id).update(
            coins=F('coins') + transfer.amount
        )
        transfer.receiver.refresh_from_db(fields=['coins'])

        CoinTransaction.objects.create(
            user=transfer.receiver,
            amount=transfer.amount,
            action='add',
            reason=f"Coin qabul qilindi: {request.user.full_name} dan {transfer.amount} coin"
        )

        # Activity log
        ActivityLog.objects.create(
            user=request.user,
            action_type='earn_coins',
            description=f"Coin ötkazdi: {transfer.receiver.full_name} ga {transfer.amount} coin"
        )
        
        # Qabul qiluvçiga telegram xabar
        if transfer.receiver.telegram_id:
            notify_user(
                transfer.receiver.telegram_id,
                f"🪙 <b>Coin qabul qildingiz!</b>\n\n"
                f"👤 Yuboruvçi: <b>{request.user.full_name}</b>\n"
                f"🪙 Miqdor: <b>{transfer.amount}</b> coin\n\n"
                f"💰 Yangi balans: <b>{transfer.receiver.coins}</b> coin"
            )
        
        # Yuboruvçiga telegram xabar
        if request.user.telegram_id:
            notify_user(
                request.user.telegram_id,
                f"✅ <b>Coin ötkazma muvaffaqiyatli!</b>\n\n"
                f"👤 Qabul qiluvçi: <b>{transfer.receiver.full_name}</b>\n"
                f"🪙 Miqdor: <b>{transfer.amount}</b> coin\n"
                f"💰 Xizmat haqqi: <b>{transfer.fee}</b> coin\n"
                f"📊 Yangi balans: <b>{request.user.coins}</b> coin"
            )
        
        # Xabar (Message)
        Message.objects.create(
            recipient=transfer.receiver,
            title=f"🪙 {request.user.full_name} sizga coin ötkazdi",
            content=f"{request.user.full_name} sizga {transfer.amount} coin ötkazdi. Yangi balansingiz: {transfer.receiver.coins} coin.",
            message_type='system'
        )
    
    api_audit.info(
        f"Coin transfer confirmed: sender={request.user.username}, "
        f"receiver={transfer.receiver.username}, amount={transfer.amount}, transfer_id={transfer.pk}"
    )
    return Response({
        'message': f"Muvaffaqiyatli! {transfer.amount} coin {transfer.receiver.full_name} ga ötkazildi.",
        'new_balance': request.user.coins,
    })
