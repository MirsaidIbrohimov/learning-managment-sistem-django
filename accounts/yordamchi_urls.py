"""Alohida Yordamchi admin paneli URL'lari (/yordamchi/*)."""

from django.urls import path

from . import yordamchi_views as v

urlpatterns = [
    # Asosiy
    path('', v.yordamchi_dashboard, name='yordamchi_dashboard'),
    path('harakatlar/', v.yordamchi_audit_log, name='yordamchi_audit_log'),
    path('profil/', v.yordamchi_profile, name='yordamchi_profile'),
    path('profil/tahrirlash/', v.yordamchi_profile_edit, name='yordamchi_profile_edit'),

    # Foydalanuvchilar
    path('oquvchilar/', v.yordamchi_students, name='yordamchi_students'),
    path('oquvchilar/<int:pk>/', v.yordamchi_student_detail, name='yordamchi_student_detail'),
    path('oqituvchilar/', v.yordamchi_teachers, name='yordamchi_teachers'),
    path('ota-onalar/', v.yordamchi_parents, name='yordamchi_parents'),

    # O'quv jarayoni (faqat ko'rish, baholash YO'Q)
    path('vazifalar/', v.yordamchi_homework, name='yordamchi_homework'),
    path('testlar/', v.yordamchi_tests, name='yordamchi_tests'),
    path('sertifikatlar/', v.yordamchi_certificates, name='yordamchi_certificates'),

    # Kutubxona
    path('kitoblar/', v.yordamchi_books, name='yordamchi_books'),
    path('kitoblar/qoshish/', v.yordamchi_book_add, name='yordamchi_book_add'),
    path('kitoblar/<int:pk>/tahrirlash/', v.yordamchi_book_edit, name='yordamchi_book_edit'),
    path('kitoblar/<int:pk>/ochirish/', v.yordamchi_book_delete, name='yordamchi_book_delete'),
    path('ijaralar/', v.yordamchi_rentals, name='yordamchi_rentals'),
    path('ijaralar/qoshish/', v.yordamchi_rental_add, name='yordamchi_rental_add'),
    path('ijaralar/<int:pk>/qaytarish/', v.yordamchi_rental_return, name='yordamchi_rental_return'),
    path('ijaralar/kechikkan/', v.yordamchi_rentals_overdue, name='yordamchi_rentals_overdue'),
    path('kitob-arizalar/', v.yordamchi_book_requests, name='yordamchi_book_requests'),
    path('kitob-arizalar/<int:pk>/tasdiqlash/', v.yordamchi_approve_book_request, name='yordamchi_approve_book_request'),
    path('kitob-arizalar/<int:pk>/rad/', v.yordamchi_reject_book_request, name='yordamchi_reject_book_request'),

    # So'rovlar & yordam
    path('sorovlar/', v.yordamchi_requests, name='yordamchi_requests'),
    path('yordam-xatlari/', v.yordamchi_help, name='yordamchi_help'),
    path('arizalar/', v.yordamchi_applications, name='yordamchi_applications'),
]
