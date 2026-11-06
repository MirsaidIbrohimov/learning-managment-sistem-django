from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [
    path('', views.post_list, name='post_list'),
    path('admin/', views.admin_posts, name='admin_posts'),
    path('create/', views.post_create, name='post_create'),
    # Eski raqamli havolalar (/blog/29/) tokenli manzilga yönaltiriladi.
    path('<int:pk>/', views.legacy_post_redirect),
    path('<str:token>/', views.post_detail, name='post_detail'),
    path('<str:token>/like/', views.toggle_like, name='toggle_like'),
    path('<str:token>/edit/', views.post_edit, name='post_edit'),
    path('<str:token>/delete/', views.post_delete, name='post_delete'),
    path('comment/<int:pk>/like/', views.toggle_comment_like, name='toggle_comment_like'),
]
