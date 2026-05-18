import logging
import math
import random
import string
from datetime import timedelta

api_audit = logging.getLogger('api.audit')

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum, Q
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from api.permissions import CoinTransferRateThrottle, IsNotBlocked
from coin.models import Product, ProductLike, ProductComment, ProductPurchase, CoinTransaction, ActivityLog, CoinTransfer
from accounts.models import CustomUser, PremiumRequest, Message
from telegram_bot.utils import notify_group, notify_user, notify_admins
from .serializers import (
    ProductSerializer, ProductCommentSerializer, ProductPurchaseSerializer,
    CoinTransactionSerializer, ActivityLogSerializer, CoinSummarySerializer,
    ProductCommentCreateSerializer, PremiumRequestSerializer,
    CoinTransferSearchResultSerializer, CoinTransferInitSerializer,
    CoinTransferConfirmSerializer, CoinTransferDetailSerializer,
)

PREMIUM_DISCOUNT = 0.05

PREMIUM_PLANS_BASE = {
    'weekly': {'name': 'Haftalik', 'days': 7, 'percent': 25},
    'monthly': {'name': '1 oylik', 'days': 30, 'percent': 50},
    'bimonthly': {'name': '2 oylik', 'days': 60, 'percent': 75},
}


def get_premium_plans_for_user(user):
    """Foydalanuvchiga mos premium narxlarni hisoblash (hozirgi balansga qarab)"""
    total_earned = user.coins
    plans = {}
    MINIMUM_PRICE = 1000
    for key, base in PREMIUM_PLANS_BASE.items():
        price = math.floor(total_earned * base['percent'] / 100)
        plans[key] = {
            'name': base['name'],
            'price': max(price, MINIMUM_PRICE),
            'days': base['days'],
            'percent': base['percent'],
        }
    return plans, total_earned


def can_user_buy_premium(user):
    """Foydalanuvchi kamida 1 oy oldin ro'yxatdan o'tganmi"""
    if not user.date_joined:
        return False
    return (timezone.now() - user.date_joined).days >= 30


def get_discounted_price(product, user):
    if user.is_premium:
        return math.floor(product.coin_price * (1 - PREMIUM_DISCOUNT))
    return product.coin_price


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
    product = get_object_or_404(Product, pk=pk)
    final_price = get_discounted_price(product, request.user)
    has_discount = request.user.is_premium and final_price < product.coin_price

    if request.user.coins < final_price:
        return Response({'error': "Coinlaringiz yetarli emas!"}, status=status.HTTP_400_BAD_REQUEST)

    if product.stock <= 0:
        return Response({'error': "Mahsulot tugagan!"}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        request.user.coins -= final_price
        request.user.save(update_fields=['coins'])

        product.stock -= 1
        product.save()

        purchase = ProductPurchase.objects.create(
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
                f"❌ Bekor qilish uchun saytga kiring."
            )

        Message.objects.create(
            recipient=request.user,
            title=f"✅ Buyurtma #{purchase.pk} qabul qilindi",
            content=f"Siz '{product.name}' mahsulotini {final_price} coin ga sotib oldingiz. Buyurtmangiz kutilmoqda. Agar bekor qilmoqchi bo'lsangiz, 'Mening xaridlarim' bo'limiga o'ting.",
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
        return Response({'error': "Bu buyurtmani bekor qilib bo'lmaydi!"}, status=status.HTTP_400_BAD_REQUEST)

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
            content=f"'{purchase.product.name}' mahsuloti uchun buyurtmangiz bekor qilindi. {purchase.coins_spent} coin balansingizga qaytarildi.",
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
            {'error': "Siz 1 soatda faqat bitta izoh qoldirishingiz mumkin! ⏰"},
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
        request.user.remove_coins(1, f"Mahsulotga izoh yozish: {product.name}")

    ActivityLog.objects.create(
        user=request.user,
        action_type='comment_product',
        description=f"Mahsulotga izoh qoldirdi: {product.name}"
    )

    return Response(ProductCommentSerializer(comment).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def request_premium(request):
    serializer = PremiumRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    plan = serializer.validated_data['plan']

    if not can_user_buy_premium(request.user):
        return Response(
            {'error': "Premium sotib olish uchun kamida 1 oy oldin ro'yxatdan o'tgan bo'lishingiz kerak!"},
            status=status.HTTP_400_BAD_REQUEST
        )

    pending = PremiumRequest.objects.filter(user=request.user, status='pending').first()
    if pending:
        return Response(
            {'error': "Sizda allaqachon kutilayotgan Premium so'rov bor!"},
            status=status.HTTP_400_BAD_REQUEST
        )

    plans, total_earned = get_premium_plans_for_user(request.user)
    plan_info = plans[plan]
    price = plan_info['price']

    if price <= 0:
        return Response(
            {'error': "Sizda yetarli coin yig'ilmagan! Premium narxi sizning umumiy yig'ilgan coinlaringizga qarab belgilanadi."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if request.user.coins < price:
        return Response(
            {'error': f"Coinlaringiz yetarli emas! {plan_info['name']} Premium narxi: {price} coin"},
            status=status.HTTP_400_BAD_REQUEST
        )

    with transaction.atomic():
        request.user.coins -= price
        request.user.save(update_fields=['coins'])

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

    label = "uzaytirish " if is_ext else ""
    return Response(
        {'message': f"Premium {label}so'rovingiz yuborildi! Admin tasdiqlashini kuting."},
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

    # Oxirgi 5 ta premium so'rovlar tarixi
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


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked])
def search_user_for_transfer(request):
    """Username yoki telefon raqam bo'yicha foydalanuvchi qidirish"""
    query = request.query_params.get('username', '').strip()
    if not query or len(query) < 2:
        return Response({'error': "Kamida 2 ta belgi kiriting"}, status=status.HTTP_400_BAD_REQUEST)
    
    base_qs = CustomUser.objects.filter(
        is_blocked=False,
    ).exclude(pk=request.user.pk)
    
    # Telefon raqam bo'yicha qidirish (raqam bilan boshlansa)
    if query.replace('+', '').replace(' ', '').replace('-', '').isdigit():
        clean_phone = query.replace(' ', '').replace('-', '')
        users = base_qs.filter(phone__icontains=clean_phone)[:5]
    else:
        # Username yoki ism bo'yicha qidirish
        users = base_qs.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )[:5]
    
    serializer = CoinTransferSearchResultSerializer(users, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsNotBlocked])
@throttle_classes([CoinTransferRateThrottle])
def initiate_transfer(request):
    """Coin o'tkazmani boshlash — tasdiqlash kodi yuborish"""
    serializer = CoinTransferInitSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    receiver_username = serializer.validated_data['receiver_username']
    amount = serializer.validated_data['amount']
    
    # Qabul qiluvchini topish
    try:
        receiver = CustomUser.objects.get(username=receiver_username, is_blocked=False)
    except CustomUser.DoesNotExist:
        return Response({'error': "Foydalanuvchi topilmadi!"}, status=status.HTTP_404_NOT_FOUND)
    
    if receiver.pk == request.user.pk:
        return Response({'error': "O'zingizga coin o'tkaza olmaysiz!"}, status=status.HTTP_400_BAD_REQUEST)
    
    # 10% xizmat haqqi
    fee = math.ceil(amount * 0.10)
    total_deducted = amount + fee
    
    if request.user.coins < total_deducted:
        return Response({
            'error': f"Coinlaringiz yetarli emas! Kerak: {total_deducted} coin ({amount} + {fee} xizmat haqqi), Balansingiz: {request.user.coins}"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Kutilayotgan o'tkazma bor-yo'qligini tekshirish
    pending = CoinTransfer.objects.filter(sender=request.user, status='pending').first()
    if pending:
        # Eskisini bekor qilish
        pending.status = 'cancelled'
        pending.save()
    
    # Tasdiqlash kodi
    code = ''.join(random.choices(string.digits, k=6))
    
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
    # Agar telegram ulangan bo'lsa — kodni telegramga yuborish
    needs_telegram = bool(request.user.telegram_id)
    if needs_telegram:
        notify_user(
            request.user.telegram_id,
            f"🔐 <b>Coin o'tkazma tasdiqlash kodi</b>\n\n"
            f"👤 Qabul qiluvchi: <b>{receiver.full_name}</b> (@{receiver.username})\n"
            f"🪙 Miqdor: <b>{amount}</b> coin\n"
            f"💰 Xizmat haqqi: <b>{fee}</b> coin\n"
            f"📊 Jami: <b>{total_deducted}</b> coin\n\n"
            f"🔑 Tasdiqlash kodi: <b>{code}</b>\n\n"
            f"⚠️ Bu kodni hech kimga bermang!"
        )
    
    data = CoinTransferDetailSerializer(transfer).data
    data['needs_telegram_code'] = needs_telegram
    return Response(data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsNotBlocked])
@throttle_classes([CoinTransferRateThrottle])
def confirm_transfer(request):
    """Coin o'tkazmani tasdiqlash"""
    serializer = CoinTransferConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    transfer_id = serializer.validated_data['transfer_id']
    
    try:
        transfer = CoinTransfer.objects.get(pk=transfer_id, sender=request.user, status='pending')
    except CoinTransfer.DoesNotExist:
        return Response({'error': "O'tkazma topilmadi yoki muddati o'tgan!"}, status=status.HTTP_404_NOT_FOUND)
    
    # Muddatni tekshirish (10 daqiqa)
    if (timezone.now() - transfer.created_at).total_seconds() > 600:
        transfer.status = 'cancelled'
        transfer.save()
        return Response({'error': "O'tkazma muddati o'tdi! Qaytadan urinib ko'ring."}, status=status.HTTP_400_BAD_REQUEST)
    
    # Tasdiqlash: telegram kodi yoki parol
    needs_telegram = bool(request.user.telegram_id)
    
    if needs_telegram:
        code = serializer.validated_data.get('code', '')
        if not code or code != transfer.verification_code:
            return Response({'error': "Tasdiqlash kodi noto'g'ri!"}, status=status.HTTP_400_BAD_REQUEST)
    else:
        password = serializer.validated_data.get('password', '')
        if not password or not request.user.check_password(password):
            return Response({'error': "Parol noto'g'ri!"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Balansni qayta tekshirish
    if request.user.coins < transfer.total_deducted:
        transfer.status = 'cancelled'
        transfer.save()
        return Response({'error': "Coinlaringiz yetarli emas!"}, status=status.HTTP_400_BAD_REQUEST)
    
    # O'tkazmani amalga oshirish
    with transaction.atomic():
        # Yuboruvchidan yechish
        request.user.coins -= transfer.total_deducted
        request.user.save(update_fields=['coins'])
        
        # Qabul qiluvchiga qo'shish
        transfer.receiver.coins += transfer.amount
        transfer.receiver.save(update_fields=['coins'])
        
        transfer.status = 'completed'
        transfer.completed_at = timezone.now()
        transfer.save()
        
        # Tranzaksiyalar yaratish
        CoinTransaction.objects.create(
            user=request.user,
            amount=transfer.total_deducted,
            action='remove',
            reason=f"Coin o'tkazma: {transfer.receiver.full_name} ga {transfer.amount} coin ({transfer.fee} xizmat haqqi)"
        )
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
            description=f"Coin o'tkazdi: {transfer.receiver.full_name} ga {transfer.amount} coin"
        )
        
        # Qabul qiluvchiga telegram xabar
        if transfer.receiver.telegram_id:
            notify_user(
                transfer.receiver.telegram_id,
                f"🪙 <b>Coin qabul qildingiz!</b>\n\n"
                f"👤 Yuboruvchi: <b>{request.user.full_name}</b>\n"
                f"🪙 Miqdor: <b>{transfer.amount}</b> coin\n\n"
                f"💰 Yangi balans: <b>{transfer.receiver.coins}</b> coin"
            )
        
        # Yuboruvchiga telegram xabar
        if request.user.telegram_id:
            notify_user(
                request.user.telegram_id,
                f"✅ <b>Coin o'tkazma muvaffaqiyatli!</b>\n\n"
                f"👤 Qabul qiluvchi: <b>{transfer.receiver.full_name}</b>\n"
                f"🪙 Miqdor: <b>{transfer.amount}</b> coin\n"
                f"💰 Xizmat haqqi: <b>{transfer.fee}</b> coin\n"
                f"📊 Yangi balans: <b>{request.user.coins}</b> coin"
            )
        
        # Xabar (Message)
        Message.objects.create(
            recipient=transfer.receiver,
            title=f"🪙 {request.user.full_name} sizga coin o'tkazdi",
            content=f"{request.user.full_name} sizga {transfer.amount} coin o'tkazdi. Yangi balansingiz: {transfer.receiver.coins} coin.",
            message_type='system'
        )
    
    api_audit.info(
        f"Coin transfer confirmed: sender={request.user.username}, "
        f"receiver={transfer.receiver.username}, amount={transfer.amount}, transfer_id={transfer.pk}"
    )
    return Response({
        'message': f"Muvaffaqiyatli! {transfer.amount} coin {transfer.receiver.full_name} ga o'tkazildi.",
        'new_balance': request.user.coins,
    })
