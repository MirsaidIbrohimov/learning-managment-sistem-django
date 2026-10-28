from django.urls import path

from . import views

app_name = 'startup'

# DIQQAT: URL nomlarida `leaderboard, rating, profile, homework, messages,
# settings, devices, help, books` substring'lari IŞLATILMAYDI —
# `accounts.middleware.SectionBlockMiddleware` url_name'ni substring böyiça
# bloklaydi va aks holda startup bölimi tasodifan yopilib qolardi.
urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('create/', views.create, name='create'),
    path('explore/', views.explore, name='explore'),
    path('top/', views.top, name='top'),
    path('mentor/', views.mentor, name='mentor'),

    path('<slug:slug>/', views.detail, name='detail'),
    path('<slug:slug>/edit/', views.edit, name='edit'),
    path('<slug:slug>/roadmap/', views.roadmap, name='roadmap'),

    path('<slug:slug>/tasks/', views.task_list, name='task_list'),
    path('<slug:slug>/tasks/new/', views.task_create, name='task_create'),
    path('<slug:slug>/tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('<slug:slug>/tasks/<int:pk>/submit/', views.task_submit, name='task_submit'),
    path('<slug:slug>/tasks/<int:pk>/review/', views.task_review, name='task_review'),

    path('<slug:slug>/team/', views.team, name='team'),
    path('<slug:slug>/team/join/', views.team_join, name='team_join'),
    path('<slug:slug>/team/invite/', views.team_invite, name='team_invite'),
    path('<slug:slug>/team/<int:pk>/respond/', views.team_respond, name='team_respond'),

    path('<slug:slug>/feedback/', views.feedback, name='feedback'),
    path('<slug:slug>/finance/', views.finance, name='finance'),
    path('<slug:slug>/finance/<int:pk>/delete/', views.finance_delete, name='finance_delete'),
    path('<slug:slug>/metrics/', views.metrics, name='metrics'),
    path('<slug:slug>/pitch/', views.pitch, name='pitch'),
]
