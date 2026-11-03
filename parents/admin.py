from django.contrib import admin
from django.utils import timezone

from .models import ParentAppToken


@admin.register(ParentAppToken)
class ParentAppTokenAdmin(admin.ModelAdmin):
    """"ITC Ota Ona" ilovasidagi kirişlar. Haş körsatilmaydi; yozuvni faqat bekor qiliş mumkin."""
    list_display = ('parent', 'device', 'created_at', 'last_used_at', 'revoked_at')
    list_filter = ('revoked_at',)
    search_fields = ('parent__first_name', 'parent__last_name', 'parent__phone', 'device')
    fields = ('parent', 'device', 'created_at', 'last_used_at', 'revoked_at')
    readonly_fields = fields
    actions = ['revoke']

    def has_add_permission(self, request):
        return False

    @admin.action(description="Tanlangan kirişlarni bekor qiliş")
    def revoke(self, request, queryset):
        queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
