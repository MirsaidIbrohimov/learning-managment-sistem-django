
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.urls import re_path

urlpatterns = [
    path("ai/", include("ai_yordamchi.urls")),
    path('admin/', admin.site.urls),
    path('teacher/', include('teacher.urls')),
    path('', include('accounts.urls')),
    path('dashboard/parents/', include('parents.urls')),
    path('parent/', include('parents.portal_urls')),
    path('', include('coin.urls')),
    path('blog/', include('blog.urls')),
    path('games/', include('games.urls')),
    path('telegrambotlms/', include('telegram_bot.urls')),
]

# Media files handling
if settings.DEBUG:
    # Development: serve media files directly
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Production: serve media files securely
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
