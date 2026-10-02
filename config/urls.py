"""
URL configuration for config project.

Root router: yahan se saare app-level URLs include hote hain.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('chatbot.urls')),
    # Uploaded files (images/audio/video) browser se dekhne ke liye — ye route
    # ALWAYS on hai (DEBUG ke bharose nahi), warna production mein media 404
    # hoti. Render free tier pe aage koi nginx nahi hai, isliye Django hi
    # media serve kar raha hai — demo ke liye theek, production mein nginx/S3.
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
