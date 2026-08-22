
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.urls import re_path

from .views import robots_txt, security_txt, sitemap_xml, serve_media

urlpatterns = [
    path("ai/", include("ai_yordamchi.urls")),
    path(settings.ADMIN_URL, admin.site.urls),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap_xml, name='sitemap_xml'),
    path('.well-known/security.txt', security_txt, name='security_txt'),
    path('security.txt', security_txt),
    path('api/v1/', include('api.urls')),
    path('quiz/', include('quiz.page_urls')),
    path('video-quiz/', include('video_quiz.urls')),
    path('teacher/', include('teacher.urls')),
    path('yordamchi/', include('accounts.yordamchi_urls')),
    path('startup/', include('startup.urls')),
    # `accounts.urls` dan oldin: admin panel route'lari `dashboard/` ostida.
    path('dashboard/startups/', include('startup.admin_urls')),
    path('', include('accounts.urls')),
    path('dashboard/parents/', include('parents.urls')),
    path('parent/', include('parents.portal_urls')),
    path('', include('coin.urls')),
    path('blog/', include('blog.urls')),
    path('games/', include('games.urls')),
    path('telegrambotlms/', include('telegram_bot.urls')),
]

# Media files handling
# DEBUG rejimida ham `serve_media` ishlatiladi: yuklangan `.html`/`.svg` fayl
# saqlangan XSS bermasligi lokal muhitda ham tekshirilishi kerak.
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve_media, name='serve_media'),
]
