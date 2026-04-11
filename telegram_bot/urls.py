from django.urls import path
from . import views

app_name = 'telegram_bot'

urlpatterns = [
    path('link/', views.link_telegram, name='link_telegram'),
    path('unlink/', views.unlink_telegram, name='unlink_telegram'),
    path('webhook/', views.bot_webhook, name='bot_webhook'),
    path('set_webhook/', views.set_webhook, name='set_webhook'),
    path('health/', views.bot_health, name='bot_health'),
    path('admin/contact/<int:pk>/', views.admin_contact_detail, name='admin_contact_detail'),
    path('admin/broadcast/', views.admin_send_broadcast, name='admin_send_broadcast'),
    path('admin/', views.admin_telegram_users, name='admin_telegram'),
    path('contact/', views.send_contact_message, name='send_contact'),
    path('phone-link/', views.phone_link, name='phone_link'),
]
