from rest_framework import serializers
from coin.models import Product, ProductLike, ProductComment, ProductPurchase, CoinTransaction, ActivityLog
from coin.pricing import get_product_price, has_product_discount


class ProductSerializer(serializers.ModelSerializer):
    likes_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.SerializerMethodField()
    discounted_price = serializers.SerializerMethodField()
    has_discount = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    is_early_access = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'token', 'name', 'description', 'image', 'coin_price', 'discounted_price', 'has_discount', 'discount_percent', 'stock', 'is_active', 'premium_only', 'is_early_access', 'public_at', 'likes_count', 'comments_count', 'is_liked', 'created_at']

    def _user(self):
        request = self.context.get('request')
        return request.user if request and request.user.is_authenticated else None

    def get_discounted_price(self, obj):
        user = self._user()
        return get_product_price(obj, user) if user else obj.coin_price

    def get_has_discount(self, obj):
        user = self._user()
        return has_product_discount(obj, user) if user else False

    def get_discount_percent(self, obj):
        return 5 if self.get_has_discount(obj) else 0

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(user=request.user).exists()
        return False


class ProductCommentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    full_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = ProductComment
        fields = ['id', 'product', 'username', 'full_name', 'content', 'created_at']
        read_only_fields = ['id', 'product', 'username', 'full_name', 'created_at']


class ProductPurchaseSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_image = serializers.ImageField(source='product.image', read_only=True)
    product_token = serializers.CharField(source='product.token', read_only=True)
    can_cancel = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProductPurchase
        fields = ['id', 'product', 'product_name', 'product_image', 'product_token', 'coins_spent', 'purchased_at', 'is_delivered', 'status', 'can_cancel', 'cancelled_at']


class CoinTransactionSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = CoinTransaction
        fields = ['id', 'amount', 'action', 'action_display', 'reason', 'created_at']


class ActivityLogSerializer(serializers.ModelSerializer):
    action_type_display = serializers.CharField(source='get_action_type_display', read_only=True)

    class Meta:
        model = ActivityLog
        fields = ['id', 'action_type', 'action_type_display', 'description', 'created_at']


class CoinSummarySerializer(serializers.Serializer):
    total_coins = serializers.IntegerField()
    total_earned = serializers.IntegerField()
    total_spent = serializers.IntegerField()
    total_transactions = serializers.IntegerField()
    is_premium = serializers.BooleanField()


class ProductCommentCreateSerializer(serializers.Serializer):
    content = serializers.CharField()


class PremiumRequestSerializer(serializers.Serializer):
    PLAN_CHOICES = [
        ('weekly', 'Haftalik'),
        ('monthly', '1 oylik'),
        ('bimonthly', '2 oylik'),
    ]
    plan = serializers.ChoiceField(choices=PLAN_CHOICES)


class UserSearchSerializer(serializers.Serializer):
    username = serializers.CharField(source='user.username', read_only=True)
    full_name = serializers.CharField(source='user.full_name', read_only=True)
    photo = serializers.ImageField(source='user.photo', read_only=True)


class CoinTransferSearchResultSerializer(serializers.Serializer):
    username = serializers.CharField()
    full_name = serializers.CharField()
    phone = serializers.SerializerMethodField()
    role = serializers.CharField()
    photo = serializers.SerializerMethodField()
    
    def get_phone(self, obj):
        phone = obj.phone or ''
        if len(phone) > 4:
            return phone[:len(phone)-4] + '****'
        return '****'
    
    def get_photo(self, obj):
        if obj.photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.photo.url)
            return obj.photo.url
        return None


class CoinTransferInitSerializer(serializers.Serializer):
    receiver_username = serializers.CharField()
    amount = serializers.IntegerField(min_value=100, max_value=10000)


class CoinTransferConfirmSerializer(serializers.Serializer):
    transfer_id = serializers.IntegerField()
    code = serializers.CharField(max_length=6, required=False, allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True)


class CoinTransferDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sender = serializers.CharField(source='sender.full_name')
    receiver = serializers.CharField(source='receiver.full_name')
    receiver_username = serializers.CharField(source='receiver.username')
    amount = serializers.IntegerField()
    fee = serializers.IntegerField()
    total_deducted = serializers.IntegerField()
    status = serializers.CharField()
    needs_telegram_code = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    
    def get_needs_telegram_code(self, obj):
        return bool(obj.sender.telegram_id)
