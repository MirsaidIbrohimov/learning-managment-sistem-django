from django.urls import path
from . import views
from . import jumanji_views
from . import teacher_views

app_name = 'games'

urlpatterns = [
    path('', views.games_list, name='games_list'),
    path('my-results/', views.my_results, name='my_results'),
    path('my-results/pdf/', views.my_results_pdf, name='my_results_pdf'),
    path('leaderboard/<int:competition_id>/', views.competition_leaderboard, name='competition_leaderboard'),
    path('leaderboard/<int:competition_id>/api/', views.competition_leaderboard_api, name='competition_leaderboard_api'),
    path('word-leaderboard/<int:competition_id>/', views.word_game_leaderboard, name='word_game_leaderboard'),

    # Spectating — slug dan OLDIN bo'lishi shart
    path('live/', views.live_games, name='live_games'),
    path('live/<int:match_id>/', views.spectate_match, name='spectate_match'),
    path('live/<int:match_id>/state/', views.spectate_state, name='spectate_state'),

    # Jumanji jonli o'yin — slug dan OLDIN bo'lishi shart
    path('jumanji/<int:session_id>/', jumanji_views.room, name='jumanji_room'),
    path('jumanji/<int:session_id>/state/', jumanji_views.state, name='jumanji_state'),
    path('jumanji/<int:session_id>/join/', jumanji_views.join, name='jumanji_join'),
    path('jumanji/<int:session_id>/leave/', jumanji_views.leave, name='jumanji_leave'),
    path('jumanji/<int:session_id>/roll/', jumanji_views.roll, name='jumanji_roll'),
    path('jumanji/<int:session_id>/control/', jumanji_views.control, name='jumanji_control'),

    # Ustoz musobaqalari (sovrin ustoz hisobidan) — slug dan OLDIN
    path('teacher/competitions/', teacher_views.competitions, name='teacher_competitions'),
    path('teacher/competitions/add/', teacher_views.competition_add, name='teacher_competition_add'),
    path('teacher/competitions/<int:pk>/edit/', teacher_views.competition_edit, name='teacher_competition_edit'),
    path('teacher/competitions/<int:pk>/toggle/', teacher_views.competition_toggle, name='teacher_competition_toggle'),
    path('teacher/competitions/<int:pk>/end/', teacher_views.competition_end, name='teacher_competition_end'),
    path('teacher/competitions/<int:pk>/delete/', teacher_views.competition_delete, name='teacher_competition_delete'),

    # Game detail & launch — slug catchall (oxirda)
    path('<slug:slug>/', views.game_detail, name='game_detail'),
    path('<slug:slug>/launch/', views.game_launch, name='game_launch'),
    path('<slug:slug>/play/', views.game_play, name='game_play'),
    path('<slug:slug>/play/<int:competition_id>/', views.game_play, name='game_play_competition'),
    # Yozish mashqi 2.0 — o'sha sessiya/submit, yangi ko'rinish
    path('<slug:slug>/v2/', views.game_play, {'ui': 'v2'}, name='game_play_v2'),
    path('<slug:slug>/v2/<int:competition_id>/', views.game_play, {'ui': 'v2'}, name='game_play_v2_competition'),
    path('<slug:slug>/submit/', views.game_submit, name='game_submit'),
    path('<slug:slug>/word-play/', views.word_game_play, name='word_game_play'),
    path('<slug:slug>/word-play/<int:competition_id>/', views.word_game_play, name='word_game_play_competition'),
    path('<slug:slug>/word-check/', views.word_game_check, name='word_game_check'),
    path('<slug:slug>/word-submit/', views.word_game_submit, name='word_game_submit'),
    path('<slug:slug>/word-suggest/', views.word_game_suggest, name='word_game_suggest'),

    # Admin
    path('dashboard/games/', views.admin_games, name='admin_games'),
    path('dashboard/games/add/', views.admin_game_add, name='admin_game_add'),
    path('dashboard/games/<int:pk>/edit/', views.admin_game_edit, name='admin_game_edit'),
    path('dashboard/games/<int:pk>/toggle/', views.admin_game_toggle, name='admin_game_toggle'),
    path('dashboard/games/<int:pk>/delete/', views.admin_game_delete, name='admin_game_delete'),
    path('dashboard/games/<int:game_pk>/prompts/', views.admin_prompts, name='admin_prompts'),
    path('dashboard/games/<int:game_pk>/prompts/add/', views.admin_prompt_add, name='admin_prompt_add'),
    path('dashboard/games/<int:game_pk>/prompts/export/', views.admin_prompts_export, name='admin_prompts_export'),
    path('dashboard/games/<int:game_pk>/prompts/import/', views.admin_prompts_import, name='admin_prompts_import'),
    path('dashboard/games/<int:game_pk>/prompts/template/', views.admin_prompts_template, name='admin_prompts_template'),
    path('dashboard/prompts/<int:pk>/edit/', views.admin_prompt_edit, name='admin_prompt_edit'),
    path('dashboard/prompts/<int:pk>/delete/', views.admin_prompt_delete, name='admin_prompt_delete'),
    path('dashboard/games/<int:game_pk>/word-rounds/', views.admin_word_rounds, name='admin_word_rounds'),
    path('dashboard/games/<int:game_pk>/word-rounds/add/', views.admin_word_round_add, name='admin_word_round_add'),
    path('dashboard/word-rounds/<int:pk>/edit/', views.admin_word_round_edit, name='admin_word_round_edit'),
    path('dashboard/word-rounds/<int:pk>/delete/', views.admin_word_round_delete, name='admin_word_round_delete'),
    path('dashboard/competitions/', views.admin_competitions, name='admin_competitions'),
    path('dashboard/competitions/add/', views.admin_competition_add, name='admin_competition_add'),
    path('dashboard/competitions/<int:pk>/edit/', views.admin_competition_edit, name='admin_competition_edit'),
    path('dashboard/competitions/<int:pk>/delete/', views.admin_competition_delete, name='admin_competition_delete'),
    path('dashboard/competitions/<int:pk>/end/', views.admin_competition_end, name='admin_competition_end'),
    path('dashboard/results/', views.admin_results, name='admin_results'),
    path('dashboard/results/pdf/', views.admin_results_pdf, name='admin_results_pdf'),
    path('dashboard/results/<int:pk>/<str:result_type>/edit/', views.admin_result_edit, name='admin_result_edit'),
    path('dashboard/results/<int:pk>/<str:result_type>/delete/', views.admin_result_delete, name='admin_result_delete'),
    path('dashboard/word-suggestions/', views.admin_word_suggestions, name='admin_word_suggestions'),
    path('dashboard/word-suggestions/<int:pk>/action/', views.admin_word_suggestion_action, name='admin_word_suggestion_action'),

    # Jumanji — admin
    path('dashboard/games/<int:game_pk>/jumanji/', jumanji_views.admin_questions, name='jumanji_admin_questions'),
    path('dashboard/games/<int:game_pk>/jumanji/add/', jumanji_views.admin_question_add, name='jumanji_admin_question_add'),
    path('dashboard/games/<int:game_pk>/jumanji/export/', jumanji_views.admin_questions_export, name='jumanji_admin_questions_export'),
    path('dashboard/games/<int:game_pk>/jumanji/import/', jumanji_views.admin_questions_import, name='jumanji_admin_questions_import'),
    path('dashboard/games/<int:game_pk>/jumanji/template/', jumanji_views.admin_questions_template, name='jumanji_admin_questions_template'),
    path('dashboard/jumanji-questions/<int:pk>/edit/', jumanji_views.admin_question_edit, name='jumanji_admin_question_edit'),
    path('dashboard/jumanji-questions/<int:pk>/delete/', jumanji_views.admin_question_delete, name='jumanji_admin_question_delete'),
    path('dashboard/jumanji-sessions/', jumanji_views.admin_sessions, name='jumanji_admin_sessions'),
    path('dashboard/competitions/<int:pk>/jumanji/open/', jumanji_views.admin_open_lobby, name='jumanji_open_lobby'),
]
