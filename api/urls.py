from django.urls import path, include
from rest_framework.authtoken.views import obtain_auth_token
from . import views
from games import external_api as games_external_api

app_name = 'api'

urlpatterns = [
    # Auth
    path('token/', obtain_auth_token, name='api_token'),
    path('status/', views.api_status, name='api_status'),

    # Profile
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/complete/', views.ProfileCompleteView.as_view(), name='profile_complete'),

    # Courses
    path('courses/', views.ProfessionListView.as_view(), name='course_list'),
    path('courses/<int:pk>/', views.ProfessionDetailView.as_view(), name='course_detail'),
    path('courses/<int:pk>/sections/', views.CourseSectionsView.as_view(), name='course_sections'),
    path('courses/<int:pk>/lessons/', views.CourseLessonsView.as_view(), name='course_lessons'),

    # Student
    path('my/enrollments/', views.MyEnrollmentsView.as_view(), name='my_enrollments'),
    path('my/test-results/', views.MyTestResultsView.as_view(), name='my_test_results'),
    path('my/certificates/', views.MyCertificatesView.as_view(), name='my_certificates'),

    # Admin
    path('admin/students/', views.AdminStudentListView.as_view(), name='admin_students'),

    # Coin
    path('coin/', include('api.coin.urls')),

    # Reyting (leaderboard)
    path('reyting/', include('api.reyting.urls')),

    # Yordamchi admin (assistant_admin) boshqaruv API
    path('assistant/', include('api.assistant.urls')),

    # External Games (tashqi o'yinlar uchun SSO + result API)
    path('games/external/verify/', games_external_api.verify, name='external_game_verify'),
    path('games/external/result/', games_external_api.submit_result, name='external_game_result'),

    # Multiplayer (Shashka uchun)
    path('games/external/mp/find/',   games_external_api.mp_find,   name='external_game_mp_find'),
    path('games/external/mp/state/',  games_external_api.mp_state,  name='external_game_mp_state'),
    path('games/external/mp/move/',   games_external_api.mp_move,   name='external_game_mp_move'),
    path('games/external/mp/resign/', games_external_api.mp_resign, name='external_game_mp_resign'),
    path('games/external/mp/room/',   games_external_api.mp_room,   name='external_game_mp_room'),

    # Gamification (XP / level / streak / achievements / leaderboard)
    path('games/external/gx/profile/',     games_external_api.gx_profile,     name='external_game_gx_profile'),
    path('games/external/gx/complete/',    games_external_api.gx_complete,    name='external_game_gx_complete'),
    path('games/external/gx/leaderboard/', games_external_api.gx_leaderboard, name='external_game_gx_leaderboard'),
]
