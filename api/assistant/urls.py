from django.urls import path
from . import views

app_name = 'assistant'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.assistant_dashboard, name='dashboard'),

    # === META: permissions, rollar, action log ===
    path('permissions/', views.permission_registry, name='permissions'),
    path('roles/', views.AssistantRoleListCreateView.as_view(), name='roles'),
    path('roles/<int:pk>/', views.AssistantRoleDetailView.as_view(), name='role_detail'),
    path('action-logs/', views.ActionLogListView.as_view(), name='action_logs'),
    path('users/<int:pk>/assign-role/', views.user_assign_role, name='user_assign_role'),

    # === O'QUV JARAYONI ===
    # Vazifalar
    path('homeworks/', views.HomeworkListView.as_view(), name='homeworks'),
    path('homework-submissions/', views.HomeworkSubmissionListView.as_view(), name='homework_submissions'),
    path('homework-submissions/<int:pk>/', views.HomeworkSubmissionUpdateView.as_view(), name='homework_submission_detail'),
    # Test hulosalari
    path('test-results/', views.TestResultListView.as_view(), name='test_results'),
    path('test-results/<int:pk>/', views.TestResultDetailView.as_view(), name='test_result_detail'),
    # Darslar tahlili
    path('lessons-analytics/', views.LessonAnalyticsListView.as_view(), name='lessons_analytics'),
    # Davomat
    path('attendance/', views.AttendanceListCreateView.as_view(), name='attendance'),
    path('attendance/<int:pk>/', views.AttendanceDetailView.as_view(), name='attendance_detail'),
    # Sertifikatlar (avtomatik beriladi — so'rovlar tizimi olib tashlangan)
    path('certificates/', views.CertificateListView.as_view(), name='certificates'),

    # === FOYDALANUVCHILAR ===
    path('users/', views.UserListView.as_view(), name='users'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/set-password/', views.user_set_password, name='user_set_password'),
    path('users/<int:pk>/toggle-block/', views.user_toggle_block, name='user_toggle_block'),
    # Parol tiklash
    path('password-resets/', views.PasswordResetRequestListView.as_view(), name='password_resets'),
    path('password-resets/<int:pk>/review/', views.password_reset_review, name='password_reset_review'),
    # Ota-onalar
    path('parents/', views.ParentListCreateView.as_view(), name='parents'),
    path('parents/<int:pk>/', views.ParentDetailView.as_view(), name='parent_detail'),
    path('parent-messages/', views.ParentMessageListView.as_view(), name='parent_messages'),
    path('parent-messages/<int:pk>/reply/', views.parent_message_reply, name='parent_message_reply'),
    path('parent-password-resets/', views.ParentPasswordResetListView.as_view(), name='parent_password_resets'),
    path('parent-password-resets/<int:pk>/review/', views.parent_password_reset_review, name='parent_password_reset_review'),
    # So'rovlar
    path('enrollment-requests/', views.EnrollmentRequestListView.as_view(), name='enrollment_requests'),
    path('enrollment-requests/<int:pk>/review/', views.enrollment_request_review, name='enrollment_request_review'),
    path('unenroll-requests/', views.UnenrollRequestListView.as_view(), name='unenroll_requests'),
    path('unenroll-requests/<int:pk>/review/', views.unenroll_request_review, name='unenroll_request_review'),
    path('premium-requests/', views.PremiumRequestListView.as_view(), name='premium_requests'),
    path('premium-requests/<int:pk>/review/', views.premium_request_review, name='premium_request_review'),

    # === KONTENT ===
    # Xabarlar
    path('messages/', views.MessageListCreateView.as_view(), name='messages'),
    path('messages/<int:pk>/', views.MessageDetailView.as_view(), name='message_detail'),
    # Blog
    path('blog/posts/', views.BlogPostListCreateView.as_view(), name='blog_posts'),
    path('blog/posts/<int:pk>/', views.BlogPostDetailView.as_view(), name='blog_post_detail'),
    path('blog/comments/', views.BlogCommentListView.as_view(), name='blog_comments'),
    path('blog/comments/<int:pk>/', views.BlogCommentDeleteView.as_view(), name='blog_comment_delete'),
    # Kutubxona
    path('books/', views.BookListCreateView.as_view(), name='books'),
    path('books/<int:pk>/', views.BookDetailView.as_view(), name='book_detail'),
    path('book-rentals/', views.BookRentalListCreateView.as_view(), name='book_rentals'),
    path('book-rentals/<int:pk>/return/', views.book_rental_return, name='book_rental_return'),

    # === SUPPORT ===
    # Yordam xatlari
    path('help-requests/', views.HelpRequestListView.as_view(), name='help_requests'),
    path('help-requests/<int:pk>/', views.HelpRequestDetailView.as_view(), name='help_request_detail'),
    path('help-requests/<int:pk>/respond/', views.help_request_respond, name='help_request_respond'),
    # Arizalar
    path('applications/', views.CourseApplicationListView.as_view(), name='applications'),
    path('applications/<int:pk>/', views.CourseApplicationDetailView.as_view(), name='application_detail'),
    # So'rovnomalar
    path('surveys/', views.SurveyFormListCreateView.as_view(), name='surveys'),
    path('surveys/<int:pk>/', views.SurveyFormDetailView.as_view(), name='survey_detail'),
    path('survey-questions/', views.SurveyQuestionListCreateView.as_view(), name='survey_questions'),
    path('survey-questions/<int:pk>/', views.SurveyQuestionDetailView.as_view(), name='survey_question_detail'),
    path('survey-responses/', views.SurveyResponseListView.as_view(), name='survey_responses'),
]
