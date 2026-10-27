from django.urls import path
from . import views

app_name = 'ai_yordamchi'

urlpatterns = [
    path('', views.chat_home, name='chat_home'),
    path('new/', views.new_session, name='new_session'),
    path('session/<int:pk>/', views.chat_session, name='chat_session'),
    path('session/<int:pk>/send/', views.send_message, name='send_message'),
    path('session/<int:pk>/generate-image/', views.generate_image, name='generate_image'),
    path('session/<int:pk>/stream/', views.stream_response, name='stream_response'),
    path('session/<int:pk>/clear/', views.clear_history, name='clear_history'),
    path('session/<int:pk>/delete/', views.delete_session, name='delete_session'),
    path('session/<int:pk>/rename/', views.rename_session, name='rename_session'),
    path('session/<int:pk>/pin/', views.toggle_pin, name='toggle_pin'),
    path('session/<int:pk>/move/', views.move_session, name='move_session'),
    path('message/<int:pk>/rate/', views.rate_message, name='rate_message'),

    # Folders
    path('folders/create/', views.create_folder, name='create_folder'),
    path('folders/<int:pk>/rename/', views.rename_folder, name='rename_folder'),
    path('folders/<int:pk>/delete/', views.delete_folder, name='delete_folder'),

    # Admin
    path('admin/chats/', views.admin_chats, name='admin_chats'),
    path('admin/chats/<int:pk>/', views.admin_chat_detail, name='admin_chat_detail'),
]
