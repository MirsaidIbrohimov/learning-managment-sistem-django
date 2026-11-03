from django.urls import path, re_path
from . import views, social_auth, legal_views
from . import payment_views
from . import tezcheck_views
from . import exam_payments
from . import course_payments
from . import public_courses
from . import password_recovery
from . import email_verification
from . import exam_admin
from . import app_releases
from . import desktop_auth
from . import certificate_designs
from . import course_bundle_views
from . import premium_views
from .api import homework_views as hw_api
from .api import chat_views as chat_api
from .api import notify_views as notify_api

urlpatterns = [
    path('', views.home_view, name='home'),
    path('daily-question/answer/', views.daily_question_answer, name='daily_question_answer'),
    path('onboarding/done/', views.onboarding_done, name='onboarding_done'),
    path('search/', views.global_search, name='global_search'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('auth/google/login/', social_auth.social_login, {'provider': 'google'}, name='google_login'),
    path('auth/google/connect/', social_auth.social_connect, {'provider': 'google'}, name='google_connect'),
    path('auth/google/callback/', social_auth.social_callback, {'provider': 'google'}, name='google_callback'),
    path('auth/google/disconnect/', social_auth.social_disconnect, {'provider': 'google'}, name='google_disconnect'),
    path('auth/facebook/login/', social_auth.social_login, {'provider': 'facebook'}, name='facebook_login'),
    path('auth/facebook/connect/', social_auth.social_connect, {'provider': 'facebook'}, name='facebook_connect'),
    path('auth/facebook/callback/', social_auth.social_callback, {'provider': 'facebook'}, name='facebook_callback'),
    path('auth/facebook/disconnect/', social_auth.social_disconnect, {'provider': 'facebook'}, name='facebook_disconnect'),
    path('auth/github/login/', social_auth.social_login, {'provider': 'github'}, name='github_login'),
    path('auth/github/connect/', social_auth.social_connect, {'provider': 'github'}, name='github_connect'),
    path('accounts/github/login/callback/', social_auth.social_callback, {'provider': 'github'}, name='github_callback'),
    path('auth/github/disconnect/', social_auth.social_disconnect, {'provider': 'github'}, name='github_disconnect'),
    path('auth/social/admin-unlink/<int:pk>/', social_auth.admin_unlink_social, name='social_admin_unlink'),
    path('auth/social/signup/', social_auth.social_signup, name='social_signup'),
    path('privacy/', legal_views.privacy_policy, name='privacy_policy'),
    path('data-deletion/', legal_views.data_deletion, name='data_deletion'),
    path('email/verify/<str:token>/', email_verification.verify_email, name='verify_email'),
    path('email/verify-resend/', email_verification.resend_verification, name='resend_email_verification'),
    path('login/location-consent/', views.login_location_consent, name='login_location_consent'),
    path('app/desktop-login/<str:request_id>/', desktop_auth.desktop_login_approve, name='desktop_login_approve'),
    path('app/web-login/<str:code>/', desktop_auth.app_web_login, name='app_web_login'),
    path('login/location-record/', views.login_location_record, name='login_location_record'),
    path('login/location-skip/', views.login_location_skip, name='login_location_skip'),
    path('logout/', views.logout_view, name='logout'),

    # Professions & Courses
    path('professions/', views.professions_view, name='professions'),
    # Oçiq (login'siz) SEO sahifalari — sotuvdagi kurslar.
    path('kurslar/', public_courses.catalog, name='public_courses'),
    path('kurslar/<int:pk>/', public_courses.course_short, name='public_course_short'),
    path('kurslar/<int:pk>-<slug:slug>/', public_courses.course_landing, name='public_course'),
    path('professions/<int:pk>/', views.profession_detail, name='profession_detail'),
    path('professions/<int:pk>/statistics/', views.course_statistics, name='course_statistics'),
    path('professions/<int:pk>/statistics/api/', views.course_statistics_api, name='course_statistics_api'),
    path('professions/<int:pk>/enroll/', views.enroll_course, name='enroll_course'),
    path('professions/<int:pk>/unenroll/', views.unenroll_course, name='unenroll_course'),
    path('professions/<int:pk>/request-certificate/', views.request_certificate, name='request_certificate'),
    path('professions/<int:pk>/manage/', views.manage_lessons, name='manage_lessons'),
    path('professions/<int:pk>/add-lesson/', views.add_lesson, name='add_lesson'),
    path('professions/<int:pk>/add-section/', views.add_section, name='add_section'),
    path('section/<int:pk>/edit/', views.edit_section, name='edit_section'),
    path('section/<int:pk>/delete/', views.delete_section, name='delete_section'),
    
    # Lessons (admin/teacher - PK based)
    path('lessons/<int:pk>/', views.lesson_view, name='lesson_view'),
    path('lessons/<int:pk>/edit/', views.edit_lesson, name='edit_lesson'),
    path('lessons/<int:pk>/delete/', views.delete_lesson, name='delete_lesson'),
    path('video/<int:pk>/watched/', views.mark_video_watched, name='mark_video_watched'),
    path('video/<int:pk>/beat/', views.video_watch_beat, name='video_watch_beat'),
    path('lessons/<int:pk>/generate-article/', views.generate_ai_article_view, name='generate_ai_article'),
    path('homework/<int:pk>/submit/', views.submit_homework, name='submit_homework'),
    path('speaking/<int:pk>/submit/', views.submit_speaking, name='submit_speaking'),
    path('homework/<int:pk>/edit/', views.edit_homework, name='edit_homework'),
    path('homework/generate-ai/', views.generate_ai_homework, name='generate_ai_homework'),
    path('test/generate-ai/', views.generate_ai_test, name='generate_ai_test'),
    
    # Tests (admin/teacher - PK based)
    path('test/<int:pk>/start/', views.start_test, name='start_test'),
    path('test/<int:pk>/submit/', views.submit_test, name='submit_test'),
    path('test/result/<int:pk>/', views.test_result, name='test_result'),
    
    # Student token-based course URL
    path('c/<uuid:token>/', views.student_course_view, name='student_course_view'),

    # Student token-based lesson URLs
    path('s/<uuid:token>/', views.student_lesson_view, name='student_lesson_view'),
    path('s/<uuid:token>/video/watched/', views.student_mark_video_watched, name='student_mark_video_watched'),
    path('s/<uuid:token>/video/beat/', views.student_video_watch_beat, name='student_video_watch_beat'),
    path('s/<uuid:token>/homework/submit/', views.student_submit_homework, name='student_submit_homework'),
    path('s/<uuid:token>/homework/edit/', views.student_edit_homework, name='student_edit_homework'),
    path('s/<uuid:token>/speaking/submit/', views.student_submit_speaking, name='student_submit_speaking'),
    path('s/<uuid:token>/test/start/', views.student_start_test, name='student_start_test'),
    path('s/<uuid:token>/test/submit/', views.student_submit_test, name='student_submit_test'),
    path('s/<uuid:token>/test/result/<int:result_pk>/', views.student_test_result, name='student_test_result'),
    path('test/<int:pk>/questions/', views.manage_test_questions, name='manage_test_questions'),
    path('test/<int:pk>/questions/add/', views.add_test_question, name='add_test_question'),
    path('question/<int:pk>/delete/', views.delete_test_question, name='delete_test_question'),
    path('test/<int:pk>/import/', views.import_test_questions, name='import_test_questions'),
    
    # Yakuniy test tölovlari
    path('test/<int:pk>/final-payment/', views.final_test_payment, name='final_test_payment'),
    path('dashboard/final-test-payments/', views.admin_final_test_payments, name='admin_final_test_payments'),
    path('dashboard/final-test-payments/<int:pk>/approve/', views.approve_final_test_payment, name='approve_final_test_payment'),
    path('dashboard/final-test-payments/<int:pk>/reject/', views.reject_final_test_payment, name='reject_final_test_payment'),
    
    # Dictionary
    path('dictionary/<int:pk>/manage/', views.manage_dictionary, name='manage_dictionary'),
    path('dictionary/<int:pk>/add-word/', views.add_dictionary_word, name='add_dictionary_word'),
    path('dictionary-word/<int:pk>/delete/', views.delete_dictionary_word, name='delete_dictionary_word'),
    path('dictionary/<int:pk>/import/', views.import_dictionary_words, name='import_dictionary_words'),
    path('dictionary/<int:pk>/ai-generate/', views.ai_generate_dictionary, name='ai_generate_dictionary'),
    
    # Profile
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),
    path('profile/customize/', premium_views.premium_customize, name='premium_customize'),
    path('profile/complete/', views.complete_profile, name='complete_profile'),
    path('profile/change-password/', views.change_password_view, name='change_password'),
    path('profile/statistics/', views.student_statistics, name='my_statistics'),
    path('profile/statistics/pdf/', views.export_student_pdf, name='my_statistics_pdf'),
    path('settings/', views.site_settings, name='site_settings'),
    path('settings/weather/', views.save_weather_effect, name='save_weather_effect'),
    path('settings/navigation/', views.save_navigation_preferences, name='save_navigation_preferences'),
    
    # Kursdoşlar va boşqa öquvçilar profili
    path('professions/<int:pk>/classmates/', views.classmates_view, name='classmates'),
    path('students/<int:pk>/', views.student_public_profile, name='student_public_profile'),
    path('teachers/<int:pk>/', views.teacher_public_profile, name='teacher_public_profile'),
    
    # Leaderboard
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    
    # Teacher panel
    path('homework-submissions/', views.homework_submissions, name='homework_submissions'),
    path('homework/<int:pk>/grade/', views.grade_homework, name='grade_homework'),
    path('homework/bulk-ai-grade/', views.bulk_ai_grade, name='bulk_ai_grade'),
    path('homework/notify-teacher/', views.notify_teacher_homework, name='notify_teacher_homework'),
    path('test-results/', views.all_test_results, name='all_test_results'),
    
    # Student test results
    path('my-test-results/', views.my_test_results, name='my_test_results'),
    
    # Student homework
    path('my-homeworks/', views.my_homework_list, name='my_homework_list'),
    path('homework/<int:pk>/chat/', views.homework_chat, name='homework_chat'),

    # ── Homework REST API ──────────────────────────────────────────────────
    path('api/hw/<int:lesson_pk>/',               hw_api.hw_detail,              name='api_hw_detail'),
    path('api/hw/<int:lesson_pk>/submit/',         hw_api.hw_submit,              name='api_hw_submit'),
    path('api/hw/<int:lesson_pk>/edit/',           hw_api.hw_edit,                name='api_hw_edit'),
    path('api/hw/<int:lesson_pk>/history/',        hw_api.hw_history,             name='api_hw_history'),
    path('api/hw/<int:lesson_pk>/messages/',       hw_api.hw_messages_list,       name='api_hw_messages_list'),
    path('api/hw/<int:lesson_pk>/messages/send/',  hw_api.hw_messages_send,       name='api_hw_messages_send'),
    path('api/hw/<int:lesson_pk>/submissions/',    hw_api.hw_teacher_submissions, name='api_hw_teacher_submissions'),
    path('api/hw/submission/<int:sub_pk>/grade/',  hw_api.hw_grade,               name='api_hw_grade'),
    # ──────────────────────────────────────────────────────────────────────
    
    # ==== ÇAT (Guruh + Şaxsiy) ====
    # Sahifalar
    path('professions/<int:pk>/chat/', views.group_chat_view, name='group_chat'),
    path('chat/', views.chat_inbox_view, name='chat_inbox'),
    path('chat/groups/', views.my_group_chats_view, name='my_group_chats'),
    path('chat/u/<int:pk>/', views.direct_chat_view, name='direct_chat'),
    path('dashboard/group-chats/', views.admin_group_chats, name='admin_group_chats'),
    path('dashboard/direct-chats/', views.admin_direct_chats, name='admin_direct_chats'),
    path('dashboard/direct-chats/ai/', views.admin_direct_chats_ai, name='admin_direct_chats_ai'),
    path('dashboard/direct-chats/<int:u1_pk>/<int:u2_pk>/', views.admin_direct_chat_detail, name='admin_direct_chat_detail'),
    # Çat API (polling)
    path('api/chat/group/<int:profession_pk>/messages/', chat_api.group_messages, name='api_chat_group_messages'),
    path('api/chat/group/<int:profession_pk>/members/',  chat_api.group_members,  name='api_chat_group_members'),
    path('api/chat/group/<int:profession_pk>/send/',     chat_api.group_send,     name='api_chat_group_send'),
    path('api/chat/direct/<int:user_pk>/messages/',      chat_api.direct_messages, name='api_chat_direct_messages'),
    path('api/chat/direct/<int:user_pk>/send/',          chat_api.direct_send,     name='api_chat_direct_send'),
    path('api/chat/conversations/',                      chat_api.conversations,   name='api_chat_conversations'),
    path('api/chat/sidebar/',                            chat_api.sidebar,         name='api_chat_sidebar'),
    path('api/chat/unread/',                             chat_api.unread_count,    name='api_chat_unread'),
    # Per-message actions (Phase 1 çat upgrade)
    path('api/chat/msg/<str:kind>/<int:msg_id>/edit/',    chat_api.message_edit,    name='api_chat_msg_edit'),
    path('api/chat/msg/<str:kind>/<int:msg_id>/delete/',  chat_api.message_delete,  name='api_chat_msg_delete'),
    path('api/chat/msg/<str:kind>/<int:msg_id>/react/',   chat_api.message_react,   name='api_chat_msg_react'),
    path('api/chat/msg/<str:kind>/<int:msg_id>/forward/', chat_api.message_forward, name='api_chat_msg_forward'),
    path('api/chat/typing/ping/',                         chat_api.typing_ping,     name='api_chat_typing_ping'),
    path('api/chat/typing/status/',                       chat_api.typing_status,   name='api_chat_typing_status'),
    path('api/chat/pin/',                                 chat_api.pin_toggle,      name='api_chat_pin_toggle'),
    path('api/chat/users/search/',                        chat_api.user_search,     name='api_chat_user_search'),

    # ── Bildirişnoma feed (barça sahifalarda real-time toast + ovoz) ──
    path('api/notify/feed/', notify_api.notify_feed, name='api_notify_feed'),
    path('api/notify/mark-all-read/', notify_api.notify_mark_all_read, name='api_notify_mark_all_read'),

    # Messages
    path('messages/', views.messages_view, name='messages'),
    path('messages/<int:pk>/', views.message_detail, name='message_detail'),
    path('messages/<int:pk>/read/', views.mark_message_read, name='mark_message_read'),
    path('messages/mark-all-read/', views.mark_all_messages_read, name='mark_all_messages_read'),
    path('messages/delete-read/', views.delete_read_messages, name='delete_read_messages'),
    
    # Admin Panel
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/export-report/', views.admin_export_report, name='admin_export_report'),
    path('dashboard/toggle-maintenance/', views.toggle_maintenance, name='toggle_maintenance'),
    path('dashboard/professions/', views.admin_professions, name='admin_professions'),
    path('dashboard/course-bundles/', course_bundle_views.admin_course_bundles, name='admin_course_bundles'),
    path('dashboard/course-bundles/<int:pk>/edit/', course_bundle_views.admin_course_bundle_edit, name='admin_course_bundle_edit'),
    path('dashboard/course-bundles/<int:pk>/delete/', course_bundle_views.admin_course_bundle_delete, name='admin_course_bundle_delete'),
    path('dashboard/course-bundles/<int:pk>/progress/', course_bundle_views.admin_course_bundle_progress, name='admin_course_bundle_progress'),
    path('dashboard/course-bundles/<int:pk>/sync/', course_bundle_views.admin_course_bundle_sync, name='admin_course_bundle_sync'),
    path('dashboard/professions/add/', views.admin_profession_add, name='admin_profession_add'),
    path('dashboard/professions/<int:pk>/edit/', views.admin_profession_edit, name='admin_profession_edit'),
    path('dashboard/professions/<int:pk>/delete/', views.admin_profession_delete, name='admin_profession_delete'),
    path('dashboard/professions/<int:pk>/toggle-block/', views.admin_profession_toggle_block, name='admin_profession_toggle_block'),
    path('dashboard/professions/<int:pk>/toggle-daily-limit/', views.admin_profession_toggle_daily_limit, name='admin_profession_toggle_daily_limit'),
    path('dashboard/professions/<int:pk>/toggle-certificate/', views.admin_profession_toggle_certificate, name='admin_profession_toggle_certificate'),
    path('dashboard/professions/<int:profession_pk>/remove-student/<int:user_pk>/', views.admin_remove_student_from_course, name='admin_remove_student_from_course'),
    path('dashboard/professions/<int:profession_pk>/add-student/', views.admin_add_student_to_course, name='admin_add_student_to_course'),
    path('dashboard/users/', views.admin_users, name='admin_users'),
    path('dashboard/users/ai/', views.admin_users_ai, name='admin_users_ai'),
    path('dashboard/users/add-teacher/', views.admin_add_teacher, name='admin_add_teacher'),
    path('dashboard/users/add-assistant-admin/', views.admin_add_assistant_admin, name='admin_add_assistant_admin'),
    path('dashboard/assistant/', views.assistant_admin_dashboard, name='assistant_admin_dashboard'),
    path('dashboard/users/export/', views.admin_export_students, name='admin_export_students'),
    
    # Admin: Öqituvçilar boşqaruvi
    path('dashboard/teachers/', views.admin_teachers, name='admin_teachers'),
    path('dashboard/teachers/export-pdf/', views.export_teachers_pdf, name='export_teachers_pdf'),
    path('dashboard/teachers/<int:pk>/ai-toggle/', views.admin_teacher_ai_toggle, name='admin_teacher_ai_toggle'),
    path('dashboard/teachers/<int:pk>/profile/', views.admin_teacher_profile, name='admin_teacher_profile'),
    path('dashboard/teachers/certificates/', views.admin_teacher_certificates, name='admin_teacher_certificates'),
    path('dashboard/teachers/attendance/', views.admin_teacher_attendance, name='admin_teacher_attendance'),
    path('dashboard/teachers/earnings/', views.admin_teacher_earnings, name='admin_teacher_earnings'),
    path('dashboard/teachers/certificates/add/', views.admin_teacher_certificate_add, name='admin_teacher_certificate_add'),
    path('dashboard/teachers/certificates/<int:pk>/delete/', views.admin_teacher_certificate_delete, name='admin_teacher_certificate_delete'),
    path('dashboard/users/<int:pk>/', views.admin_user_view, name='admin_user_view'),
    path('dashboard/users/<int:pk>/edit/', views.admin_user_edit, name='admin_user_edit'),
    path('dashboard/users/<int:pk>/block/', views.admin_user_block, name='admin_user_block'),
    path('dashboard/users/<int:pk>/unlink-telegram/', views.admin_unlink_telegram, name='admin_unlink_telegram'),
    path('dashboard/users/<int:pk>/finished/', views.admin_user_finished, name='admin_user_finished'),
    path('dashboard/users/<int:pk>/delete/', views.admin_user_delete, name='admin_user_delete'),
    path('dashboard/users/<int:user_pk>/daily-limit/<int:profession_pk>/', views.admin_user_daily_limit, name='admin_user_daily_limit'),
    path('dashboard/users/<int:user_pk>/final-exam/<int:profession_pk>/<int:quiz_pk>/grant-retry/', exam_admin.admin_grant_exam_retry, name='admin_grant_exam_retry'),
    path('dashboard/users/<int:pk>/statistics/', views.student_statistics, name='user_statistics'),
    path('dashboard/users/<int:pk>/statistics/pdf/', views.export_student_pdf, name='user_statistics_pdf'),
    path('dashboard/users/<int:pk>/certificate/', views.issue_certificate, name='issue_certificate'),
    path('dashboard/test-analytics/', views.admin_test_analytics, name='admin_test_analytics'),
    path('dashboard/test-result/<int:pk>/', views.admin_test_result_detail, name='admin_test_result_detail'),
    path('dashboard/export-pdf/', views.export_system_pdf, name='export_system_pdf'),
    path('dashboard/messages/', views.admin_messages, name='admin_messages'),
    path('dashboard/messages/send/', views.admin_send_message, name='admin_send_message'),
    
    # Admin: Sections
    path('dashboard/sections/', views.admin_sections, name='admin_sections'),
    path('dashboard/sections/add/', views.admin_section_add, name='admin_section_add'),
    path('dashboard/sections/<int:pk>/edit/', views.admin_section_edit, name='admin_section_edit'),
    path('dashboard/sections/<int:pk>/delete/', views.admin_section_delete, name='admin_section_delete'),
    
    # Admin: Page/Section Management
    path('dashboard/sections-management/', views.admin_sections_management, name='admin_sections_management'),
    re_path(r'^dashboard/sections-management/(?P<section>[\w-]+)/toggle/$', views.toggle_section_block, name='toggle_section_block'),
    
    # Help Requests / Yordam
    path('help/', views.help_page, name='help_page'),
    path('help/submit/', views.submit_help_request, name='submit_help_request'),
    path('dashboard/help_requests/', views.admin_help_requests, name='admin_help_requests'),
    path('dashboard/help-requests/<int:pk>/', views.admin_help_request_detail, name='admin_help_request_detail'),
    
    # Coin Management
    path('dashboard/coins/', views.admin_manage_coins, name='admin_manage_coins'),
    
    # Darslar statistikasi
    path('dashboard/lesson-statistics/', views.admin_lesson_statistics, name='admin_lesson_statistics'),

    # Guruhlar & Dars jadvali (Admin & Assistant Admin)
    path('dashboard/study-groups/', views.admin_study_groups, name='admin_study_groups'),
    path('dashboard/study-groups/create/', views.admin_study_group_create, name='admin_study_group_create'),
    path('dashboard/study-groups/<int:pk>/edit/', views.admin_study_group_edit, name='admin_study_group_edit'),
    path('dashboard/study-groups/<int:pk>/delete/', views.admin_study_group_delete, name='admin_study_group_delete'),

    # Foydalanuvçi uçun şaxsiy dars jadvali
    path('my-schedule/', views.my_study_schedule, name='my_study_schedule'),

    # Öquvçilar davomati (Teacher & Assistant Admin & Admin)
    path('attendance/', views.attendance_home, name='attendance_home'),
    path('attendance/group/<int:group_pk>/', views.attendance_mark, name='attendance_mark'),
    path('attendance/group/<int:group_pk>/report/', views.attendance_report, name='attendance_report'),
    path('attendance/group/<int:group_pk>/report/excel/', views.attendance_report_excel, name='attendance_report_excel'),

    # Ilovalar boşqaruvi (Android / Windows örnatuvçilari)
    path('dashboard/apps/', app_releases.admin_app_releases, name='admin_app_releases'),
    path('dashboard/apps/<int:pk>/edit/', app_releases.admin_app_release_edit, name='admin_app_release_edit'),
    path('dashboard/apps/<int:pk>/toggle/', app_releases.admin_app_release_toggle, name='admin_app_release_toggle'),
    path('dashboard/apps/<int:pk>/delete/', app_releases.admin_app_release_delete, name='admin_app_release_delete'),
    path('ilovalar/', app_releases.apps_page, name='apps_page'),
    path('ilovalar/<int:pk>/download/', app_releases.app_release_download, name='app_release_download'),

    # Discounts / Çegirmalar
    path('dashboard/discounts/', views.admin_discounts, name='admin_discounts'),
    path('dashboard/discounts/add/', views.admin_discount_add, name='admin_discount_add'),
    path('dashboard/discounts/<int:pk>/edit/', views.admin_discount_edit, name='admin_discount_edit'),
    path('dashboard/discounts/<int:pk>/delete/', views.admin_discount_delete, name='admin_discount_delete'),
    
    # Qurilmalar boşqaruvi (User)
    path('profile/devices/', views.my_devices, name='my_devices'),
    path('profile/devices/<int:pk>/remove/', views.remove_device, name='remove_device'),
    path('profile/devices/<int:pk>/logout/', views.logout_device, name='logout_device'),
    path('profile/devices/<int:pk>/trust/', views.trust_device, name='trust_device'),
    path('profile/devices/logout-all/', views.logout_all_devices, name='logout_all_devices'),
    path('profile/devices/remove-all/', views.remove_all_devices, name='remove_all_devices'),
    path('profile/devices/bulk-remove/', views.bulk_remove_devices, name='bulk_remove_devices'),
    path('profile/sessions/<int:pk>/logout/', views.logout_session, name='logout_session'),

    # Admin: Qurilmalar
    path('dashboard/users/<int:pk>/devices/', views.admin_user_devices, name='admin_user_devices'),
    path('dashboard/users/<int:user_pk>/devices/<int:device_pk>/logout/', views.admin_logout_user_device, name='admin_logout_user_device'),
    path('dashboard/users/<int:pk>/devices/logout-all/', views.admin_logout_all_user_devices, name='admin_logout_all_user_devices'),
    
    # Admin: Hisobotlar
    
    # Admin: Kursga yoziliş sörovlari
    path('dashboard/enrollment-requests/', views.admin_enrollment_requests, name='admin_enrollment_requests'),
    path('dashboard/enrollment-requests/<int:pk>/approve/', views.approve_enrollment_request, name='approve_enrollment_request'),
    path('dashboard/enrollment-requests/<int:pk>/reject/', views.reject_enrollment_request, name='reject_enrollment_request'),
    
    # Admin: Kursdan çiqiş sörovlari
    path('dashboard/unenroll-requests/', views.admin_unenroll_requests, name='admin_unenroll_requests'),
    path('dashboard/unenroll-requests/<int:pk>/approve/', views.approve_unenroll_request, name='approve_unenroll_request'),
    path('dashboard/unenroll-requests/<int:pk>/reject/', views.reject_unenroll_request, name='reject_unenroll_request'),
    
    # Parol tiklaş
    path('password-reset-request/', views.password_reset_request_view, name='password_reset_request'),
    path('password-reset-captcha/', password_recovery.password_recovery_captcha, name='password_reset_captcha'),
    path('password-reset/open/<str:token>/', password_recovery.open_recovery_link, name='open_recovery_link'),
    path('password-reset/set-password/', password_recovery.choose_recovery_password, name='choose_recovery_password'),
    
    # Kutubxona / Kitoblar
    path('dashboard/books/', views.admin_books, name='admin_books'),
    path('dashboard/books/check/', views.book_check_duplicate, name='book_check_duplicate'),
    path('dashboard/book-requests/', views.admin_book_requests, name='admin_book_requests'),
    path('dashboard/books/add/', views.admin_book_add, name='admin_book_add'),
    path('dashboard/books/<int:pk>/edit/', views.admin_book_edit, name='admin_book_edit'),
    path('dashboard/books/<int:pk>/delete/', views.admin_book_delete, name='admin_book_delete'),
    path('dashboard/book-rentals/', views.admin_book_rentals, name='admin_book_rentals'),
    path('dashboard/book-rentals/give/', views.admin_give_book, name='admin_give_book'),
    path('dashboard/book-rentals/<int:pk>/return/', views.admin_return_book, name='admin_return_book'),
    
    # Admin: Premium boşqaruv
    path('dashboard/premium/', views.admin_premium_management, name='admin_premium_management'),
    path('dashboard/premium/<int:pk>/approve/', views.approve_premium_request, name='approve_premium_request'),
    path('dashboard/premium/<int:pk>/reject/', views.reject_premium_request, name='reject_premium_request'),
    
    # Öquvçi: Kutubxona sahifasi (API orqali)
    path('library/', views.student_library, name='student_library'),
    path('my-books/', views.my_book_rentals, name='my_book_rentals'),

    # Premium reklama flagini tozalaş
    path('clear-premium-ad/', views.clear_premium_ad, name='clear_premium_ad'),
    path('clear-ai-ad/', views.clear_ai_ad, name='clear_ai_ad'),

    # Admin: Öquvçi sertifikatlari
    path('dashboard/certificates/', views.admin_certificates, name='admin_certificates'),
    path('dashboard/certificates/issue/', views.admin_certificate_issue, name='admin_certificate_issue'),
    path('dashboard/certificates/settings/', views.admin_certificate_settings, name='admin_certificate_settings'),
    path('dashboard/certificates/manual/', views.admin_certificate_manual, name='admin_certificate_manual'),
    path('dashboard/certificates/designs/', certificate_designs.admin_certificate_designs, name='admin_certificate_designs'),
    path('dashboard/certificates/designs/<int:pk>/', certificate_designs.admin_certificate_design_edit, name='admin_certificate_design_edit'),
    path('dashboard/certificates/designs/<int:pk>/preview/', certificate_designs.admin_certificate_design_preview, name='admin_certificate_design_preview'),
    path('dashboard/certificates/designs/<int:pk>/delete/', certificate_designs.admin_certificate_design_delete, name='admin_certificate_design_delete'),
    path('dashboard/certificates/<int:pk>/status/', views.admin_certificate_status, name='admin_certificate_status'),
    path('dashboard/certificates/<int:pk>/edit/', views.admin_certificate_edit, name='admin_certificate_edit'),
    path('dashboard/certificates/<int:pk>/regenerate/', views.admin_certificate_regenerate, name='admin_certificate_regenerate'),
    path('dashboard/certificates/<int:pk>/delete/', views.admin_certificate_delete, name='admin_certificate_delete'),
    path('certificate/<int:pk>/download/', views.download_certificate, name='download_certificate'),
    
    # Sertifikat tekşiriş (login talab qilinmaydi)
    path('verify-certificate/', views.verify_certificate, name='verify_certificate'),
    
    # Ariza
    path('ariza/', views.ariza_view, name='ariza'),
    # Keep the previous URL available for existing links while promoting the new brand URL.
    path('dashboard/applications/', views.admin_applications, name='admin_applications'),
    path('dashboard/applications/<int:pk>/status/', views.admin_application_status, name='admin_application_status'),
    
    # Admin: AI Tekşiruvçi
    # Admin: Xavfsizlik paneli
    path('dashboard/security/', views.admin_security_events, name='admin_security_events'),
    path('dashboard/security/block-ip/', views.admin_security_block_ip, name='admin_security_block_ip'),

    # Admin: AI Tekşiruvçi
    path('dashboard/ai-checker/', views.admin_ai_checker, name='admin_ai_checker'),
    path('dashboard/ai-checker/toggle/', views.admin_ai_checker_toggle, name='admin_ai_checker_toggle'),
    path('dashboard/ai-checker/course-toggle/', views.admin_ai_course_toggle, name='admin_ai_course_toggle'),
    path('dashboard/ai-checker/file-only-toggle/', views.admin_file_only_toggle, name='admin_file_only_toggle'),
    
    # Admin: Sörovnomalar
    path('dashboard/surveys/', views.admin_surveys, name='admin_surveys'),
    path('dashboard/surveys/create/', views.admin_survey_create, name='admin_survey_create'),
    path('dashboard/surveys/<int:pk>/edit/', views.admin_survey_edit, name='admin_survey_edit'),
    path('dashboard/surveys/<int:pk>/delete/', views.admin_survey_delete, name='admin_survey_delete'),
    path('dashboard/surveys/<int:pk>/responses/', views.admin_survey_responses, name='admin_survey_responses'),
    path('dashboard/surveys/<int:pk>/responses/excel/', views.admin_survey_responses_excel, name='admin_survey_responses_excel'),
    path('dashboard/surveys/<int:pk>/toggle/', views.admin_survey_toggle, name='admin_survey_toggle'),
    
    # Sörovnomani töldiriş
    path('survey/<int:pk>/fill/', views.fill_survey, name='fill_survey'),

    # Online tölov (Payme & Click)
    path('tezcheck/create-payment/', tezcheck_views.tezcheck_create_payment, name='tezcheck_create_payment'),
    path('tezcheck/exam/<str:kind>/<int:pk>/', exam_payments.create_exam_checkout, name='exam_checkout'),
    path('tezcheck/exam-status/<int:pk>/', exam_payments.exam_checkout_status, name='exam_checkout_status'),
    path('tezcheck/course/<int:pk>/', course_payments.create_course_checkout, name='course_checkout'),
    path('kurs/<int:pk>/balansdan/', course_payments.pay_course_from_balance, name='course_balance_pay'),
    path('tezcheck/course-status/<int:pk>/', course_payments.course_checkout_status, name='course_checkout_status'),
    path('tezcheck/return/', tezcheck_views.tezcheck_return, name='tezcheck_return'),
    path('tezcheck/webhook/', tezcheck_views.tezcheck_webhook, name='tezcheck_webhook'),
    # Kabinetda "/" siz yozilgan URL uçun: APPEND_SLASH POST'ni 301 qiladi, Tezcheck uni kuzatmaydi.
    path('tezcheck/webhook', tezcheck_views.tezcheck_webhook),
    path('inpay/webhook/', tezcheck_views.inpay_webhook, name='inpay_webhook'),
    # Kabinetda "/" siz yozilgan URL uçun: APPEND_SLASH POST'ni 301 qiladi, inPAY uni kuzatmaydi.
    path('inpay/webhook', tezcheck_views.inpay_webhook),
    path('payme/', payment_views.payme_endpoint, name='payme_endpoint'),
    path('click/prepare/', payment_views.click_prepare, name='click_prepare'),
    path('click/complete/', payment_views.click_complete, name='click_complete'),

    # Balans tizimi
    path('tolov/', views.payment_wall, name='payment_wall'),
    path('tolovlarim/', views.payment_wall, name='student_payments'),
    path('dashboard/balans/', views.admin_balance_management, name='admin_balance_management'),
    path('dashboard/balans/<int:student_id>/topup/', views.admin_balance_topup, name='admin_balance_topup'),
    path('dashboard/balans/<int:student_id>/deduct/', views.admin_balance_deduct, name='admin_balance_deduct'),
    path('dashboard/balans/<int:student_id>/history/', views.admin_balance_history, name='admin_balance_history'),
    path('dashboard/balans/<int:student_id>/set-fee/', views.admin_balance_set_fee, name='admin_balance_set_fee'),
    path('yordamchi/balans/', views.yordamchi_balance_management, name='yordamchi_balance_management'),

    # Oylik tölovlar
    path('dashboard/tezcheck/', tezcheck_views.admin_tezcheck_payments, name='admin_tezcheck_payments'),
    path('dashboard/tezcheck/<int:pk>/sync/', tezcheck_views.admin_sync_tezcheck_payment, name='admin_sync_tezcheck_payment'),

    # Yordamçi admin — alohida sahifalar
]
