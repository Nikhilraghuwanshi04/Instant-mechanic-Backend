import re

from django.utils import timezone
from rest_framework import serializers

from .models import Booking, Conversation, Diagnosis, MediaUpload, Message


class ChatRequestSerializer(serializers.Serializer):
    """POST /api/chat/ ke incoming JSON ko validate karta hai."""

    message = serializers.CharField(
        max_length=2000,
        error_messages={
            'required': 'Message is required.',
            'blank': 'Message cannot be empty.',
            'max_length': 'Message is too long (max 2000 characters).',
        },
    )
    conversation_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        error_messages={
            'invalid': 'conversation_id must be a positive integer.',
            'min_value': 'conversation_id must be a positive integer.',
        },
    )


class MessageSerializer(serializers.ModelSerializer):
    """Message object ko JSON mein convert karta hai (response ke liye)."""

    class Meta:
        model = Message
        fields = ('id', 'role', 'content', 'generated_by', 'created_at')


class ConversationSummarySerializer(serializers.ModelSerializer):
    """Conversation ko history sidebar ke liye halka-phulka JSON banata hai.

    message_count view ke annotate() se aata hai (har conversation ke liye
    alag COUNT query nahi chalti). last_message_preview last message ka
    chhota sa text hai — sidebar mein dikhane ke liye.
    """

    message_count = serializers.IntegerField(read_only=True)
    last_message_preview = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            'id',
            'title',
            'status',
            'created_at',
            'updated_at',
            'message_count',
            'last_message_preview',
        )

    def get_last_message_preview(self, obj):
        # Message.Meta.ordering = ['created_at'], isliye .last() = sabse naya.
        last = obj.messages.last()
        if last is None:
            return None
        text = last.content.strip()
        return text[:80] + '…' if len(text) > 80 else text


class UploadRequestSerializer(serializers.Serializer):
    """POST /api/upload/ ke multipart form-data ko validate karta hai."""

    file = serializers.FileField(
        error_messages={
            'required': 'No file was submitted.',
            'empty': 'The submitted file is empty.',
        },
    )
    conversation_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        error_messages={
            'invalid': 'conversation_id must be a positive integer.',
            'min_value': 'conversation_id must be a positive integer.',
        },
    )


class MediaUploadSerializer(serializers.ModelSerializer):
    """MediaUpload object ko JSON mein convert karta hai (response ke liye)."""

    class Meta:
        model = MediaUpload
        fields = (
            'id',
            'file',
            'media_type',
            'original_name',
            'size_bytes',
            'mime_type',
            'analysis_status',
            'created_at',
        )


class DiagnosisRequestSerializer(serializers.Serializer):
    """POST /api/diagnosis/ ke incoming JSON ko validate karta hai."""

    conversation_id = serializers.IntegerField(
        min_value=1,
        error_messages={
            'required': 'conversation_id is required for a diagnosis.',
            'invalid': 'conversation_id must be a positive integer.',
            'min_value': 'conversation_id must be a positive integer.',
        },
    )


class DiagnosisSerializer(serializers.ModelSerializer):
    """Diagnosis object ko JSON mein convert karta hai (response ke liye)."""

    class Meta:
        model = Diagnosis
        fields = (
            'id',
            'likely_issue',
            'reasoning',
            'confidence',
            'can_drive',
            'next_step',
            'recommended_service',
            'generated_by',
            'summary',
            'created_at',
        )


class BookingRequestSerializer(serializers.Serializer):
    """POST /api/booking/ ke incoming JSON ko validate karta hai."""

    diagnosis_id = serializers.IntegerField(
        min_value=1,
        error_messages={
            'required': 'diagnosis_id is required to book a mechanic.',
            'invalid': 'diagnosis_id must be a positive integer.',
            'min_value': 'diagnosis_id must be a positive integer.',
        },
    )
    customer_name = serializers.CharField(
        max_length=100,
        error_messages={
            'required': 'Customer name is required.',
            'blank': 'Customer name cannot be empty.',
            'max_length': 'Customer name is too long (max 100 characters).',
        },
    )
    phone = serializers.CharField(
        max_length=20,
        error_messages={
            'required': 'Phone number is required.',
            'blank': 'Phone number cannot be empty.',
            'max_length': 'Phone number is too long (max 20 characters).',
        },
    )
    preferred_date = serializers.DateField(
        error_messages={
            'required': 'Preferred date is required.',
            'invalid': 'Preferred date must be a valid date (YYYY-MM-DD).',
        },
    )

    def validate_phone(self, value):
        if not re.fullmatch(r'\+?[0-9][0-9\s\-]{6,19}', value):
            raise serializers.ValidationError('Enter a valid phone number.')
        return value

    def validate_preferred_date(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError('Preferred date cannot be in the past.')
        return value


class BookingSerializer(serializers.ModelSerializer):
    """Booking object ko JSON mein convert karta hai (response ke liye)."""

    diagnosis_id = serializers.IntegerField(read_only=True)
    conversation_id = serializers.IntegerField(
        source='diagnosis.conversation_id', read_only=True
    )
    likely_issue = serializers.CharField(
        source='diagnosis.likely_issue', read_only=True
    )

    class Meta:
        model = Booking
        fields = (
            'id',
            'booking_ref',
            'diagnosis_id',
            'conversation_id',
            'likely_issue',
            'customer_name',
            'phone',
            'preferred_date',
            'status',
            'created_at',
            'updated_at',
        )
