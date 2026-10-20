from django.urls import include, path
from config.urls import urlpatterns as project_urls

urlpatterns = [path('__debug__/', include('debug_toolbar.urls')), *project_urls]
