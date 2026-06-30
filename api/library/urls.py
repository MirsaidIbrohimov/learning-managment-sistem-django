from django.urls import path
from . import views

app_name = 'library'

urlpatterns = [
    # ─── Statistika ───
    path('stats/', views.library_stats, name='stats'),

    # ─── Duplicate tekshiruv ───
    path('books/check/', views.check_duplicate, name='check_duplicate'),

    # ─── Kitoblar (student & admin) ───
    path('books/', views.BookListView.as_view(), name='book_list'),
    path('books/<int:pk>/', views.BookDetailView.as_view(), name='book_detail'),
    path('books/<int:pk>/request/', views.request_book, name='request_book'),

    # ─── Student: mening arizalarim va ijaralarim ───
    path('my/requests/', views.MyRentalRequestsView.as_view(), name='my_requests'),
    path('my/requests/<int:pk>/cancel/', views.cancel_request, name='cancel_request'),
    path('my/rentals/', views.MyRentalsView.as_view(), name='my_rentals'),

    # ─── Admin: kitoblar CRUD ───
    path('admin/books/', views.AdminBookListCreateView.as_view(), name='admin_book_list'),
    path('admin/books/<int:pk>/', views.AdminBookDetailView.as_view(), name='admin_book_detail'),

    # ─── Admin: arizalar ───
    path('admin/requests/', views.AdminRequestListView.as_view(), name='admin_request_list'),
    path('admin/requests/<int:pk>/approve/', views.approve_request, name='approve_request'),
    path('admin/requests/<int:pk>/reject/', views.reject_request, name='reject_request'),

    # ─── Admin: ijaralar ───
    path('admin/rentals/', views.AdminRentalListView.as_view(), name='admin_rental_list'),
    path('admin/rentals/<int:pk>/return/', views.return_rental, name='return_rental'),
]
