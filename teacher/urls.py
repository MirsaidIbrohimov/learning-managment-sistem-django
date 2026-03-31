from django.urls import path
from . import views

app_name = 'teacher'

urlpatterns = [
    # Dashboard
    path('', views.teacher_dashboard, name='dashboard'),
    path('statistics/', views.teacher_statistics, name='statistics'),

    # Kurslarim
    path('courses/', views.teacher_courses, name='courses'),

    # Balans
    path('balance/', views.teacher_balance, name='balance'),

    # Test natijalari
    path('test-results/', views.teacher_test_results, name='test_results'),

    # Uyga vazifalar
    path('homeworks/', views.teacher_homeworks, name='homeworks'),
    path('homeworks/<int:pk>/grade/', views.teacher_grade_homework, name='grade_homework'),

    # Test yuklash
    path('courses/<int:pk>/add-test/', views.teacher_add_test, name='add_test'),
    path('tests/<int:pk>/questions/', views.teacher_manage_questions, name='manage_questions'),
    path('tests/<int:pk>/questions/add/', views.teacher_add_question, name='add_question'),
    path('questions/<int:pk>/delete/', views.teacher_delete_question, name='delete_question'),
    path('tests/<int:pk>/import/', views.teacher_import_questions, name='import_questions'),
    path('tests/<int:pk>/generate-ai/', views.teacher_generate_ai_test, name='generate_ai_test'),

    # Sertifikatlarim
    path('certificates/', views.teacher_certificates, name='certificates'),
    path('certificates/<int:pk>/edit/', views.teacher_certificate_edit, name='certificate_edit'),
    path('certificates/<int:pk>/toggle/', views.teacher_certificate_toggle, name='certificate_toggle'),
    path('certificates/<int:pk>/delete/', views.teacher_certificate_delete, name='certificate_delete'),
]
