from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import ChatSession, ChatMessage


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ['role', 'content_preview', 'image_preview', 'coins_spent', 'created_at']
    can_delete = True
    fields = ['role', 'content_preview', 'image_preview', 'coins_spent', 'created_at']
    
    def content_preview(self, obj):
        if obj.content:
            preview = obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
            return format_html('<div style="max-width: 300px; word-wrap: break-word;">{}</div>', preview)
        return '-'
    content_preview.short_description = "Xabar"
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-width: 100px; max-height: 100px; border-radius: 4px;" />', obj.image.url)
        return '-'
    image_preview.short_description = "Rasm"


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user_link', 'title', 'message_count', 'total_coins', 'created_at', 'updated_at', 'is_active', 'actions_column']
    list_filter = ['is_active', 'created_at', 'updated_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'title']
    readonly_fields = ['created_at', 'updated_at', 'message_count_display', 'total_coins_display']
    inlines = [ChatMessageInline]
    list_per_page = 25
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Asosiy ma\'lumotlar', {
            'fields': ('user', 'title', 'is_active')
        }),
        ('Statistika', {
            'fields': ('message_count_display', 'total_coins_display', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_link(self, obj):
        url = reverse('admin:accounts_customuser_change', args=[obj.user.pk])
        return format_html('<a href="{}">{}</a>', url, obj.user.full_name)
    user_link.short_description = "Foydalanuvçi"
    user_link.admin_order_field = 'user__first_name'
    
    def message_count(self, obj):
        count = obj.messages.count()
        if count > 0:
            url = reverse('ai_yordamchi:admin_chat_detail', args=[obj.pk])
            return format_html('<a href="{}"><strong>{}</strong></a>', url, count)
        return count
    message_count.short_description = "Xabarlar"
    message_count.admin_order_field = 'messages__count'
    
    def message_count_display(self, obj):
        return obj.messages.count()
    message_count_display.short_description = "Xabarlar soni"
    
    def total_coins(self, obj):
        total = sum(msg.coins_spent for msg in obj.messages.all())
        if total > 0:
            return format_html('<span style="color: #f59e0b; font-weight: 600;">{} coin</span>', total)
        return '0 coin'
    total_coins.short_description = "Sarflangan coin"
    
    def total_coins_display(self, obj):
        return sum(msg.coins_spent for msg in obj.messages.all())
    total_coins_display.short_description = "Jami sarflangan coin"
    
    # Admin list column for quick actions (rename to avoid clashing with ModelAdmin.actions)
    def actions_column(self, obj):
        detail_url = reverse('ai_yordamchi:admin_chat_detail', args=[obj.pk])
        return format_html(
            '<a href="{}" class="button" title="Batafsil köriş">👁️</a>',
            detail_url
        )
    actions_column.short_description = "Amallar"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user').prefetch_related('messages')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'session_link', 'role_badge', 'content_preview', 'image_preview', 'coins_spent', 'created_at']
    list_filter = ['role', 'created_at', 'coins_spent']
    search_fields = ['content', 'session__user__username', 'session__title']
    readonly_fields = ['created_at', 'image_preview_large']
    list_per_page = 50
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Asosiy ma\'lumotlar', {
            'fields': ('session', 'role', 'content', 'coins_spent', 'created_at')
        }),
        ('Rasm', {
            'fields': ('image', 'image_preview_large'),
            'classes': ('collapse',)
        }),
    )
    
    def session_link(self, obj):
        url = reverse('admin:ai_yordamchi_chatsession_change', args=[obj.session.pk])
        detail_url = reverse('ai_yordamchi:admin_chat_detail', args=[obj.session.pk])
        return format_html(
            '<a href="{}">{}</a> | <a href="{}" target="_blank">👁️</a>',
            url, obj.session.title[:30], detail_url
        )
    session_link.short_description = "Suhbat"
    session_link.admin_order_field = 'session__title'
    
    def role_badge(self, obj):
        if obj.role == 'user':
            color = '#0d6efd'
            icon = '👤'
        else:
            color = '#10b981'
            icon = '🤖'
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px;">{} {}</span>',
            color, icon, obj.get_role_display()
        )
    role_badge.short_description = "Rol"
    role_badge.admin_order_field = 'role'
    
    def content_preview(self, obj):
        if obj.content:
            preview = obj.content[:80] + '...' if len(obj.content) > 80 else obj.content
            return format_html('<div style="max-width: 400px; word-wrap: break-word;">{}</div>', preview)
        return '-'
    content_preview.short_description = "Xabar"
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-width: 60px; max-height: 60px; border-radius: 4px;" />', obj.image.url)
        return '-'
    image_preview.short_description = "Rasm"
    
    def image_preview_large(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-width: 500px; max-height: 500px; border-radius: 8px;" />', obj.image.url)
        return 'Rasm yöq'
    image_preview_large.short_description = "Rasm körinişi"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('session', 'session__user')
