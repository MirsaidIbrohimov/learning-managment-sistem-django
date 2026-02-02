from django.urls import path

from accounts.parent_views import (
    parent_login_view,
    parent_logout_view,
    parent_dashboard,
    parent_children,
    parent_lessons,
    parent_homework,
    parent_tests,
    parent_achievements,
    parent_messages,
    parent_profile,
    parent_profile_edit,
    parent_change_password,
    parent_settings,
)

urlpatterns = [
    path('parent/login/', parent_login_view, name='parent_login'),
    path('logout/', parent_logout_view, name='parent_logout'),
    path('', parent_dashboard, name='parent_dashboard'),
    path('children/', parent_children, name='parent_children'),
    path('lessons/', parent_lessons, name='parent_lessons'),
    path('homework/', parent_homework, name='parent_homework'),
    path('tests/', parent_tests, name='parent_tests'),
    path('achievements/', parent_achievements, name='parent_achievements'),
    path('messages/', parent_messages, name='parent_messages'),
    path('profile/', parent_profile, name='parent_profile'),
    path('profile/edit/', parent_profile_edit, name='parent_profile_edit'),
    path('profile/password/', parent_change_password, name='parent_change_password'),
    path('settings/', parent_settings, name='parent_settings'),
]
