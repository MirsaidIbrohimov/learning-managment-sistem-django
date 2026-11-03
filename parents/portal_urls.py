from django.urls import path

from . import app_api
from . import portal_views as v

urlpatterns = [
    path('login/', v.parent_login_view, name='parent_login'),
    path('logout/', v.parent_logout_view, name='parent_logout'),
    path('', v.parent_dashboard, name='parent_dashboard'),
    path('children/', v.parent_children, name='parent_children'),
    path('children/<int:child_id>/', v.parent_child_detail, name='parent_child_detail'),
    path('lessons/', v.parent_lessons, name='parent_lessons'),
    path('homework/', v.parent_homework, name='parent_homework'),
    path('tests/', v.parent_tests, name='parent_tests'),
    path('attendance/', v.parent_attendance, name='parent_attendance'),
    path('payments/', v.parent_payments, name='parent_payments'),
    path('payments/checkout/', v.parent_payment_checkout, name='parent_payment_checkout'),
    path('payments/return/', v.parent_payment_return, name='parent_payment_return'),
    path('achievements/', v.parent_achievements, name='parent_achievements'),
    path('books/', v.parent_books, name='parent_books'),
    path('messages/', v.parent_messages, name='parent_messages'),
    path('profile/', v.parent_profile, name='parent_profile'),
    path('profile/edit/', v.parent_profile_edit, name='parent_profile_edit'),
    path('profile/password/', v.parent_change_password, name='parent_change_password'),
    path('settings/', v.parent_settings, name='parent_settings'),
    path('password-reset/', v.parent_password_reset_request, name='parent_password_reset_request'),
    path('app-login/<str:code>/', app_api.web_login, name='parent_app_web_login'),
]
