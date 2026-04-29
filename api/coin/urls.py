from django.urls import path
from . import views

urlpatterns = [
    # Coin summary
    path('summary/', views.coin_summary, name='coin_summary'),

    # Products
    path('products/', views.ProductListView.as_view(), name='coin_products'),
    path('products/<int:pk>/', views.ProductDetailView.as_view(), name='coin_product_detail'),
    path('products/<int:pk>/comments/', views.ProductCommentsView.as_view(), name='coin_product_comments'),

    # Product actions
    path('products/<int:pk>/like/', views.toggle_like, name='coin_toggle_like'),
    path('products/<int:pk>/purchase/', views.purchase_product, name='coin_purchase_product'),
    path('products/<int:pk>/comments/add/', views.add_comment, name='coin_add_comment'),

    # Purchases
    path('my-purchases/', views.MyPurchasesView.as_view(), name='coin_my_purchases'),
    path('purchases/<int:pk>/cancel/', views.cancel_purchase, name='coin_cancel_purchase'),

    # Transactions
    path('transactions/', views.CoinTransactionListView.as_view(), name='coin_transactions'),

    # Activity
    path('activities/', views.ActivityLogListView.as_view(), name='coin_activities'),

    # Premium
    path('premium/plans/', views.premium_plans, name='coin_premium_plans'),
    path('premium/request/', views.request_premium, name='coin_request_premium'),
]
