from django.urls import path
from . import views

app_name = 'telegram_bot'

urlpatterns = [
    path('link/', views.link_telegram, name='link_telegram'),
    path('unlink/', views.unlink_telegram, name='unlink_telegram'),
    path('webhook/', views.bot_webhook, name='bot_webhook'),
    path('admin/', views.admin_telegram_users, name='admin_telegram'),
]
