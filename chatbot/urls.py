from django.urls import path

from . import views

urlpatterns = [
    path('health/', views.health_check, name='health-check'),
    path('chat/', views.chat, name='chat'),
    path('upload/', views.upload_media, name='upload-media'),
    path('diagnosis/', views.diagnosis, name='diagnosis'),
    path('booking/', views.booking, name='booking'),
    path('booking/<int:booking_id>/', views.booking_detail, name='booking-detail'),
    path('conversations/', views.conversation_list, name='conversation-list'),
    path(
        'conversations/<int:conversation_id>/',
        views.conversation_detail,
        name='conversation-detail',
    ),
]
