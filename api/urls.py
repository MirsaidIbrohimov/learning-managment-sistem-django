from django.urls import path, include
from rest_framework.authtoken.views import obtain_auth_token
from . import views

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
]
