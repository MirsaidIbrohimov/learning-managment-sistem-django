from django.urls import path
from . import views

app_name = 'games'

urlpatterns = [
    # Student: O'yinlar
    path('', views.games_list, name='games_list'),
    path('my-results/', views.my_results, name='my_results'),
    path('my-results/pdf/', views.my_results_pdf, name='my_results_pdf'),
    path('leaderboard/<int:competition_id>/', views.competition_leaderboard, name='competition_leaderboard'),
    path('<slug:slug>/', views.game_detail, name='game_detail'),
    path('<slug:slug>/play/', views.game_play, name='game_play'),
    path('<slug:slug>/play/<int:competition_id>/', views.game_play, name='game_play_competition'),
    path('<slug:slug>/submit/', views.game_submit, name='game_submit'),

    # Word Builder: Student
    path('<slug:slug>/word-play/', views.word_game_play, name='word_game_play'),
    path('<slug:slug>/word-play/<int:competition_id>/', views.word_game_play, name='word_game_play_competition'),
    path('<slug:slug>/word-check/', views.word_game_check, name='word_game_check'),
    path('<slug:slug>/word-submit/', views.word_game_submit, name='word_game_submit'),
    path('<slug:slug>/word-suggest/', views.word_game_suggest, name='word_game_suggest'),
    path('word-leaderboard/<int:competition_id>/', views.word_game_leaderboard, name='word_game_leaderboard'),

    # Admin: O'yinlar boshqaruvi
    path('dashboard/games/', views.admin_games, name='admin_games'),
    path('dashboard/games/add/', views.admin_game_add, name='admin_game_add'),
    path('dashboard/games/<int:pk>/edit/', views.admin_game_edit, name='admin_game_edit'),
    path('dashboard/games/<int:pk>/delete/', views.admin_game_delete, name='admin_game_delete'),

    # Admin: Promptlar
    path('dashboard/games/<int:game_pk>/prompts/', views.admin_prompts, name='admin_prompts'),
    path('dashboard/games/<int:game_pk>/prompts/add/', views.admin_prompt_add, name='admin_prompt_add'),
    path('dashboard/prompts/<int:pk>/edit/', views.admin_prompt_edit, name='admin_prompt_edit'),
    path('dashboard/prompts/<int:pk>/delete/', views.admin_prompt_delete, name='admin_prompt_delete'),

    # Admin: Word Builder raundlar
    path('dashboard/games/<int:game_pk>/word-rounds/', views.admin_word_rounds, name='admin_word_rounds'),
    path('dashboard/games/<int:game_pk>/word-rounds/add/', views.admin_word_round_add, name='admin_word_round_add'),
    path('dashboard/word-rounds/<int:pk>/edit/', views.admin_word_round_edit, name='admin_word_round_edit'),
    path('dashboard/word-rounds/<int:pk>/delete/', views.admin_word_round_delete, name='admin_word_round_delete'),

    # Admin: Musobaqalar
    path('dashboard/competitions/', views.admin_competitions, name='admin_competitions'),
    path('dashboard/competitions/add/', views.admin_competition_add, name='admin_competition_add'),
    path('dashboard/competitions/<int:pk>/edit/', views.admin_competition_edit, name='admin_competition_edit'),
    path('dashboard/competitions/<int:pk>/delete/', views.admin_competition_delete, name='admin_competition_delete'),
    path('dashboard/competitions/<int:pk>/end/', views.admin_competition_end, name='admin_competition_end'),

    # Admin: Natijalar
    path('dashboard/results/', views.admin_results, name='admin_results'),
    path('dashboard/results/pdf/', views.admin_results_pdf, name='admin_results_pdf'),
    path('dashboard/results/<int:pk>/<str:result_type>/delete/', views.admin_result_delete, name='admin_result_delete'),

    # Admin: So'z takliflari
    path('dashboard/word-suggestions/', views.admin_word_suggestions, name='admin_word_suggestions'),
    path('dashboard/word-suggestions/<int:pk>/action/', views.admin_word_suggestion_action, name='admin_word_suggestion_action'),
]
