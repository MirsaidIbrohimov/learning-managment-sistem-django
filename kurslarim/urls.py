from django.urls import include, path
from rest_framework.routers import SimpleRouter

from accounts.api import homework_views as hw_api

from . import views
from .access import portal_lesson_api

app_name = 'kurslarim'

router = SimpleRouter()
router.register('attempts', views.PortalAttemptViewSet, basename='attempt')

urlpatterns = [
    path('', views.my_courses, name='my_courses'),
    path('<int:pk>/', views.course_detail, name='course'),
    path('<int:pk>/qayta-yozilish/', views.rejoin_course, name='rejoin'),
    path('dars/<int:lesson_pk>/', views.lesson_detail, name='lesson'),
    path('dars/<int:lesson_pk>/qayta-topshirish/', views.quiz_retry, name='quiz_retry'),
    path('dars/<int:lesson_pk>/video/beat/', views.video_beat, name='video_beat'),
    path('dars/<int:lesson_pk>/video/watched/', views.video_watched, name='video_watched'),
    path('video-quiz/<int:video_id>/', views.video_quiz_list, name='video_quiz_list'),
    path('video-quiz/submit/', views.video_quiz_submit, name='video_quiz_submit'),

    # Uyga vazifa API — mavjud funksiyalar, kurs tekshiruvi bilan o'ralgan.
    path('api/hw/', views.api_root, name='hw_root'),
    path('api/hw/<int:lesson_pk>/', portal_lesson_api(hw_api.hw_detail), name='hw_detail'),
    path('api/hw/<int:lesson_pk>/submit/', portal_lesson_api(hw_api.hw_submit), name='hw_submit'),
    path('api/hw/<int:lesson_pk>/edit/', portal_lesson_api(hw_api.hw_edit), name='hw_edit'),
    path('api/hw/<int:lesson_pk>/history/', portal_lesson_api(hw_api.hw_history), name='hw_history'),
    path('api/hw/<int:lesson_pk>/messages/', portal_lesson_api(hw_api.hw_messages_list), name='hw_messages'),
    path('api/hw/<int:lesson_pk>/messages/send/', portal_lesson_api(hw_api.hw_messages_send), name='hw_messages_send'),

    # Test API — mavjud Attempt API, faqat sotib olingan kurslar.
    path('api/quiz/', views.api_root, name='quiz_api_root'),
    path('api/quiz/', include(router.urls)),
]
