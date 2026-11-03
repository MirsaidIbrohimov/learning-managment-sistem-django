"""Native ilova marşrutlari: /api/v1/app/..."""
from django.urls import path

from accounts.api import chat_views as chat
from accounts.api import homework_views as hw
from video_quiz.views import api_player_submit

from . import app_lessons as views
from .app_lessons import bridged

urlpatterns = [
    path('courses/<int:pk>/lessons/', views.course_lessons, name='app_course_lessons'),
    path('lessons/<int:pk>/', views.lesson_detail, name='app_lesson_detail'),
    path('lessons/<int:pk>/video/beat/', views.video_beat, name='app_video_beat'),
    path('lessons/<int:pk>/video/complete/', views.video_complete, name='app_video_complete'),
    path('lessons/<int:pk>/speaking/', views.speaking_submit, name='app_speaking_submit'),
    path('lessons/<int:pk>/test/start/', views.legacy_test_start, name='app_test_start'),
    path('lessons/<int:pk>/test/submit/', views.legacy_test_submit, name='app_test_submit'),
    path('lessons/<int:pk>/test/result/', views.legacy_test_result, name='app_test_result'),
    path('video-quiz/submit/', bridged(api_player_submit), name='app_video_quiz_submit'),

    # Vazifa
    path('lessons/<int:lesson_pk>/homework/submit/', bridged(hw.hw_submit), name='app_hw_submit'),
    path('lessons/<int:lesson_pk>/homework/edit/', bridged(hw.hw_edit), name='app_hw_edit'),
    path('lessons/<int:lesson_pk>/homework/history/', bridged(hw.hw_history), name='app_hw_history'),
    path('lessons/<int:lesson_pk>/homework/messages/', bridged(hw.hw_messages_list), name='app_hw_messages'),
    path('lessons/<int:lesson_pk>/homework/messages/send/', bridged(hw.hw_messages_send), name='app_hw_messages_send'),
    path('homework/', views.my_homework, name='app_my_homework'),

    # Jadval va xabarlar
    path('schedule/', views.my_schedule, name='app_schedule'),
    path('messages/', views.my_messages, name='app_messages'),
    path('messages/<int:pk>/read/', views.message_read, name='app_message_read'),

    # Çat
    path('chat/conversations/', bridged(chat.conversations), name='app_chat_conversations'),
    path('chat/sidebar/', bridged(chat.sidebar), name='app_chat_sidebar'),
    path('chat/unread/', bridged(chat.unread_count), name='app_chat_unread'),
    path('chat/users/search/', bridged(chat.user_search), name='app_chat_search'),
    path('chat/group/<int:profession_pk>/messages/', bridged(chat.group_messages), name='app_chat_group_messages'),
    path('chat/group/<int:profession_pk>/send/', bridged(chat.group_send), name='app_chat_group_send'),
    path('chat/direct/<int:user_pk>/messages/', bridged(chat.direct_messages), name='app_chat_direct_messages'),
    path('chat/direct/<int:user_pk>/send/', bridged(chat.direct_send), name='app_chat_direct_send'),
]
