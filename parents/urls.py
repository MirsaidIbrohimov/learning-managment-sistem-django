from django.urls import path
from . import views

app_name = 'parents'

urlpatterns = [
    path('', views.admin_parents, name='admin_parents'),
    path('add/', views.admin_parent_add, name='admin_parent_add'),
    path('<int:pk>/', views.admin_parent_view, name='admin_parent_view'),
    path('<int:pk>/edit/', views.admin_parent_edit, name='admin_parent_edit'),
    path('<int:pk>/toggle/', views.admin_parent_toggle, name='admin_parent_toggle'),
    path('<int:pk>/delete/', views.admin_parent_delete, name='admin_parent_delete'),
    path('messages/', views.admin_parent_messages, name='admin_parent_messages'),
    path('password-requests/', views.admin_parent_password_requests, name='admin_parent_password_requests'),
    path('password-requests/<int:pk>/approve/', views.approve_parent_password_reset, name='approve_parent_password_reset'),
    path('password-requests/<int:pk>/reject/', views.reject_parent_password_reset, name='reject_parent_password_reset'),
]
