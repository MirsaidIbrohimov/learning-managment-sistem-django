from django.urls import path
from . import views
from . import payments

app_name = 'coin'

urlpatterns = [
    # Frontend Pages (API-backed)
    path('coin-history/', views.coin_history, name='coin_history'),
    path('coin-transfer/', views.coin_transfer, name='coin_transfer'),
    path('market/', views.market_list, name='market_list'),
    path('market/coins/checkout/', payments.create_coin_checkout, name='coin_checkout'),
    path('market/coins/pricing/', payments.coin_pricing, name='coin_pricing'),
    path('market/coins/<int:pk>/return/', payments.coin_payment_return, name='coin_payment_return'),
    path('market/coins/<int:pk>/status/', payments.coin_payment_status, name='coin_payment_status'),
    path('market/premium/', views.premium_page, name='buy_premium'),
    path('market/buy-premium/', views.buy_premium_page, name='buy_premium_page'),
    path('market/extend-premium/', views.extend_premium_page, name='extend_premium_page'),
    path('market/<int:pk>/', views.market_detail, name='market_detail'),
    path('market/my-purchases/', views.my_purchases, name='my_purchases'),
    
    # Admin: Products
    path('dashboard/products/', views.admin_products, name='admin_products'),
    path('dashboard/products/add/', views.admin_product_add, name='admin_product_add'),
    path('dashboard/products/<int:pk>/edit/', views.admin_product_edit, name='admin_product_edit'),
    path('dashboard/products/<int:pk>/delete/', views.admin_product_delete, name='admin_product_delete'),
    path('dashboard/purchases/', views.admin_purchases, name='admin_purchases'),
    path('dashboard/purchases/<int:pk>/delivered/', views.admin_mark_delivered, name='admin_mark_delivered'),
    path('dashboard/purchases/<int:pk>/cancel/', views.admin_cancel_purchase, name='admin_cancel_purchase'),
    
    # Admin: Activities
    
    # Admin: Transfers
    path('dashboard/transfers/', views.admin_transfers, name='admin_transfers'),
]
