from django.contrib import admin

from .models import Booking, Conversation, Diagnosis, MediaUpload, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'status', 'vehicle_make', 'vehicle_model', 'vehicle_year', 'updated_at')
    list_filter = ('status',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'role', 'generated_by', 'short_content', 'created_at')
    list_filter = ('role', 'generated_by')

    @admin.display(description='content')
    def short_content(self, obj):
        return obj.content[:60]


@admin.register(MediaUpload)
class MediaUploadAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'media_type', 'original_name', 'size_bytes', 'analysis_status', 'created_at')
    list_filter = ('media_type', 'analysis_status')


@admin.register(Diagnosis)
class DiagnosisAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'likely_issue', 'confidence', 'can_drive', 'generated_by', 'created_at')
    list_filter = ('confidence', 'generated_by')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'booking_ref', 'customer_name', 'phone', 'preferred_date', 'status', 'created_at')
    list_filter = ('status',)
