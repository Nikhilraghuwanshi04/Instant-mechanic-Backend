"""
URL configuration for config project.

Root router: yahan se saare app-level URLs include hote hain.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('chatbot.urls')),
]

if settings.DEBUG:
    # Dev mein uploaded files (images/audio/video) browser se dekhne ke liye
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
