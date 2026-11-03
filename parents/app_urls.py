""""ITC Ota Ona" ilovasi marşrutlari: /api/v1/parent-app/..."""
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from . import app_api as v

# Token sarlavha orqali keladi (cookie emas), şuning uçun CSRF tekşiruvi kerak emas.
urlpatterns = [path(route, csrf_exempt(view), name=name) for route, view, name in [
    ('login/', v.login, 'parent_app_login'),
    ('logout/', v.logout, 'parent_app_logout'),
    ('password-reset/', v.password_reset, 'parent_app_password_reset'),
    ('me/', v.me, 'parent_app_me'),
    ('me/password/', v.change_password, 'parent_app_password'),
    ('children/<int:child_id>/', v.overview, 'parent_app_overview'),
    ('children/<int:child_id>/lessons/', v.lessons, 'parent_app_lessons'),
    ('children/<int:child_id>/homework/', v.homework, 'parent_app_homework'),
    ('children/<int:child_id>/tests/', v.tests, 'parent_app_tests'),
    ('children/<int:child_id>/attendance/', v.attendance, 'parent_app_attendance'),
    ('children/<int:child_id>/payments/', v.payments, 'parent_app_payments'),
    ('children/<int:child_id>/pay/', v.pay_link, 'parent_app_pay'),
    ('children/<int:child_id>/achievements/', v.achievements, 'parent_app_achievements'),
    ('children/<int:child_id>/books/', v.books, 'parent_app_books'),
    ('messages/', v.messages_view, 'parent_app_messages'),
    ('notifications/', v.notifications, 'parent_app_notifications'),
]]
