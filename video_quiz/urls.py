from django.urls import path

from . import views

app_name = 'video_quiz'

urlpatterns = [
    # Ustoz sahifalari
    path('teacher/', views.teacher_videos, name='teacher_videos'),
    path('teacher/video/<int:video_id>/', views.teacher_manager, name='teacher_manager'),

    # Ustoz/Admin API
    path('api/video/<int:video_id>/quizzes/', views.api_video_quizzes, name='api_video_quizzes'),
    path('api/video/<int:video_id>/quizzes/create/', views.api_quiz_create, name='api_quiz_create'),
    path('api/video/<int:video_id>/quizzes/ai-generate/', views.api_quiz_ai_generate, name='api_quiz_ai_generate'),
    path('api/video/<int:video_id>/quizzes/ai-save/', views.api_quiz_ai_bulk_save, name='api_quiz_ai_bulk_save'),
    path('api/quiz/<int:pk>/update/', views.api_quiz_update, name='api_quiz_update'),
    path('api/quiz/<int:pk>/delete/', views.api_quiz_delete, name='api_quiz_delete'),
    path('api/quiz/<int:pk>/toggle/', views.api_quiz_toggle, name='api_quiz_toggle'),
    path('api/quiz/<int:pk>/duplicate/', views.api_quiz_duplicate, name='api_quiz_duplicate'),

    # Öquvçi pleer API
    path('api/player/<int:video_id>/', views.api_player_quizzes, name='api_player_quizzes'),
    path('api/player/submit/', views.api_player_submit, name='api_player_submit'),

    # Admin sahifasi
    path('admin/', views.admin_quiz_list, name='admin_list'),

    # Öquvçi tarixi
    path('history/', views.student_history, name='student_history'),
]

# Bu fayl: video-quiz modulining URL marşrutlari (sahifalar + JSON API).
