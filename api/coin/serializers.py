from rest_framework import serializers
from coin.models import Product, ProductLike, ProductComment, ProductPurchase, CoinTransaction, ActivityLog


class ProductSerializer(serializers.ModelSerializer):
    likes_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'image', 'coin_price', 'stock', 'is_active', 'likes_count', 'comments_count', 'is_liked', 'created_at']

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
    can_cancel = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProductPurchase
        fields = ['id', 'product', 'product_name', 'product_image', 'coins_spent', 'purchased_at', 'is_delivered', 'status', 'can_cancel', 'cancelled_at']


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
