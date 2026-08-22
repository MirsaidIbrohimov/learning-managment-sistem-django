"""Admin panel route'lari — `dashboard/startups/` prefiksi ostida.

Nega `startup/urls.py` ga qo'shilmadi: u yerda `path('<slug:slug>/', detail)`
catch-all bor, ya'ni slug'i `export` yoki `import` bo'lgan startup admin
sahifasini soyada qoldirardi. Alohida prefiks bu xatarni yo'q qiladi va
mavjud `dashboard/users/`, `dashboard/statistics/` konvensiyasiga mos tushadi.

DIQQAT: statik segmentlar (`export/`, `import/`, `submission/`) `<slug:slug>/`
dan OLDIN turishi shart.
"""

from django.urls import path

from . import admin_views

app_name = 'startup_admin'

urlpatterns = [
    path('', admin_views.startup_list, name='startup_list'),

    path('export/', admin_views.startup_export, name='startup_export'),
    path('import/', admin_views.startup_import, name='startup_import'),
    path('import/template/', admin_views.startup_import_template,
         name='startup_import_template'),
    path('submission/<int:pk>/review/', admin_views.submission_review,
         name='submission_review'),

    path('<slug:slug>/', admin_views.startup_detail, name='startup_detail'),
    path('<slug:slug>/edit/', admin_views.startup_edit, name='startup_edit'),
    path('<slug:slug>/status/', admin_views.startup_status, name='startup_status'),
    path('<slug:slug>/delete/', admin_views.startup_delete, name='startup_delete'),
    path('<slug:slug>/mentor/', admin_views.startup_mentor, name='startup_mentor'),
    path('<slug:slug>/recompute/', admin_views.startup_recompute, name='startup_recompute'),
    path('<slug:slug>/xp/', admin_views.startup_xp, name='startup_xp'),
]
