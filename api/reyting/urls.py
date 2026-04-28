from django.urls import path
from . import views

urlpatterns = [
    path('', views.leaderboard_api, name='leaderboard_api'),
]
