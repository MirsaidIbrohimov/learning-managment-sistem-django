from django.urls import path

from . import views

# URL nomlari ataylab `leaderboard`/`rating` so'zlaridan xoli:
# `SectionBlockMiddleware` url_name ichidan substring qidiradi va "reyting"
# bo'limi bloklansa API HTML "bloklangan" sahifasini qaytarib qo'yardi.
urlpatterns = [
    path('top/', views.leaderboard, name='startup_top'),
    path('me/', views.me, name='startup_me'),
    path('<slug:slug>/', views.detail, name='startup_detail'),
    path('<slug:slug>/progress/', views.progress, name='startup_progress'),
    path('<slug:slug>/tasks/', views.tasks, name='startup_tasks'),
    path('<slug:slug>/team/', views.team, name='startup_team'),
    path('<slug:slug>/metrics/', views.metrics, name='startup_metrics'),
    path('<slug:slug>/finance/', views.finance, name='startup_finance'),
    path('<slug:slug>/pitch/', views.pitch, name='startup_pitch'),
]
