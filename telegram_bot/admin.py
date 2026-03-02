from django.contrib import admin
from .models import TelegramLoginCode, TelegramLinkToken


@admin.register(TelegramLoginCode)
class TelegramLoginCodeAdmin(admin.ModelAdmin):
    list_display = ['telegram_id', 'code', 'created_at', 'is_used']
    list_filter = ['is_used']
    search_fields = ['telegram_id', 'code']


@admin.register(TelegramLinkToken)
class TelegramLinkTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'token', 'created_at', 'is_used']
    list_filter = ['is_used']
    search_fields = ['user__username', 'token']
