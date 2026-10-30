from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum
from .models import Product, ProductLike, ProductComment, ProductPurchase, CoinTransaction, ActivityLog, CoinTransfer, PromoCode, PromoRedemption


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'coin_price', 'stock', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    list_editable = ['is_active', 'stock']


@admin.register(ProductLike)
class ProductLikeAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'created_at']
    list_filter = ['created_at']


@admin.register(ProductComment)
class ProductCommentAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'created_at']
    list_filter = ['created_at']
    search_fields = ['content']


@admin.register(ProductPurchase)
class ProductPurchaseAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'coins_spent', 'is_delivered', 'purchased_at']
    list_filter = ['is_delivered', 'purchased_at']
    list_editable = ['is_delivered']


@admin.register(CoinTransaction)
class CoinTransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'amount', 'reason', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'reason']


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action_type', 'description', 'created_at']
    list_filter = ['action_type', 'created_at']
    search_fields = ['user__username', 'description']


@admin.register(CoinTransfer)
class CoinTransferAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'colored_sender',
        'direction_arrow',
        'colored_receiver',
        'coin_badge',
        'fee_display',
        'total_display',
        'status_badge',
        'created_at',
    ]
    list_filter = ['status', 'created_at']
    search_fields = [
        'sender__username', 'sender__first_name', 'sender__last_name',
        'receiver__username', 'receiver__first_name', 'receiver__last_name',
    ]
    readonly_fields = [
        'sender', 'receiver', 'amount', 'fee', 'total_deducted',
        'verification_code', 'status', 'created_at', 'completed_at',
        'transfer_summary',
    ]
    list_per_page = 30
    list_select_related = ['sender', 'receiver']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']

    fieldsets = (
        ('👥 Ötkazma ma\'lumotlari', {
            'fields': ('transfer_summary',),
        }),
        ('📤 Yuboruvçi', {
            'fields': ('sender',),
        }),
        ('📥 Qabul qiluvçi', {
            'fields': ('receiver',),
        }),
        ('🪙 Moliyaviy ma\'lumotlar', {
            'fields': ('amount', 'fee', 'total_deducted'),
        }),
        ('📋 Holat', {
            'fields': ('status', 'created_at', 'completed_at'),
        }),
        ('🔐 Xavfsizlik', {
            'fields': ('verification_code',),
            'classes': ('collapse',),
        }),
    )

    def colored_sender(self, obj):
        return format_html(
            '<span style="color:#e74c3c;font-weight:600;">'
            '📤 {}</span><br>'
            '<small style="color:#999;">@{}</small>',
            obj.sender.full_name, obj.sender.username
        )
    colored_sender.short_description = 'Yuboruvçi'
    colored_sender.admin_order_field = 'sender__first_name'

    def direction_arrow(self, obj):
        return format_html(
            '<span style="font-size:1.3rem;color:#f39c12;">➜</span>'
        )
    direction_arrow.short_description = ''

    def colored_receiver(self, obj):
        return format_html(
            '<span style="color:#27ae60;font-weight:600;">'
            '📥 {}</span><br>'
            '<small style="color:#999;">@{}</small>',
            obj.receiver.full_name, obj.receiver.username
        )
    colored_receiver.short_description = 'Qabul qiluvçi'
    colored_receiver.admin_order_field = 'receiver__first_name'

    def coin_badge(self, obj):
        return format_html(
            '<span style="background:#fff3cd;color:#856404;padding:4px 10px;'
            'border-radius:8px;font-weight:700;font-size:0.9em;">'
            '🪙 {}</span>',
            obj.amount
        )
    coin_badge.short_description = 'Miqdor'
    coin_badge.admin_order_field = 'amount'

    def fee_display(self, obj):
        return format_html(
            '<span style="color:#e67e22;font-weight:600;">{}  <small style="color:#999;">coin</small></span>',
            obj.fee
        )
    fee_display.short_description = 'Xizmat haqqi'
    fee_display.admin_order_field = 'fee'

    def total_display(self, obj):
        return format_html(
            '<span style="color:#c0392b;font-weight:700;">{} <small style="color:#999;">coin</small></span>',
            obj.total_deducted
        )
    total_display.short_description = 'Jami yeçilgan'
    total_display.admin_order_field = 'total_deducted'

    def status_badge(self, obj):
        colors = {
            'completed': ('#d4edda', '#155724', '✅'),
            'pending':   ('#fff3cd', '#856404', '⏳'),
            'cancelled': ('#f8d7da', '#721c24', '❌'),
        }
        bg, fg, icon = colors.get(obj.status, ('#e2e3e5', '#383d41', '❓'))
        label = obj.get_status_display()
        return format_html(
            '<span style="background:{};color:{};padding:4px 12px;'
            'border-radius:10px;font-weight:600;font-size:0.85em;white-space:nowrap;">'
            '{} {}</span>',
            bg, fg, icon, label
        )
    status_badge.short_description = 'Holat'
    status_badge.admin_order_field = 'status'

    def transfer_summary(self, obj):
        return format_html(
            '<div style="background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;'
            'padding:20px 24px;border-radius:14px;font-size:0.95em;line-height:1.8;">'
            '<div style="font-size:1.2em;font-weight:700;margin-bottom:8px;">🔄 Ötkazma #{}</div>'
            '<div>📤 <b>Yuboruvçi:</b> {} <small style="opacity:0.6;">(@{})</small></div>'
            '<div>📥 <b>Qabul qiluvçi:</b> {} <small style="opacity:0.6;">(@{})</small></div>'
            '<div style="margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.15);">'
            '🪙 <b>Miqdor:</b> <span style="color:#f1c40f;font-size:1.1em;">{} coin</span> &nbsp;|&nbsp; '
            '💸 <b>Xizmat haqqi:</b> <span style="color:#e67e22;">{} coin</span> &nbsp;|&nbsp; '
            '📊 <b>Jami:</b> <span style="color:#e74c3c;font-weight:700;">{} coin</span></div>'
            '</div>',
            obj.pk,
            obj.sender.full_name, obj.sender.username,
            obj.receiver.full_name, obj.receiver.username,
            obj.amount, obj.fee, obj.total_deducted,
        )
    transfer_summary.short_description = 'Ötkazma xulosasi'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        qs = self.get_queryset(request)
        completed = qs.filter(status='completed')
        extra_context['title'] = format_html(
            '🔄 Coin Ötkazmalar &nbsp;|&nbsp; '
            '✅ {} ta muvaffaqiyatli &nbsp;|&nbsp; '
            '🪙 {} coin ötkazilgan &nbsp;|&nbsp; '
            '💰 {} coin xizmat haqqi',
            completed.count(),
            completed.aggregate(s=Sum('amount'))['s'] or 0,
            completed.aggregate(s=Sum('fee'))['s'] or 0,
        )
        return super().changelist_view(request, extra_context=extra_context)


class PromoRedemptionInline(admin.TabularInline):
    model = PromoRedemption
    extra = 0
    readonly_fields = ['user', 'coins', 'balance_after', 'created_at']
    can_delete = False


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'owner', 'max_uses', 'min_coins', 'max_coins', 'expires_at', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['code', 'owner__username', 'owner__first_name', 'owner__last_name']
    raw_id_fields = ['owner', 'created_by']
    inlines = [PromoRedemptionInline]


@admin.register(PromoRedemption)
class PromoRedemptionAdmin(admin.ModelAdmin):
    list_display = ['promo', 'user', 'coins', 'balance_after', 'created_at']
    search_fields = ['promo__code', 'user__username']
    raw_id_fields = ['promo', 'user']
