from uuid import uuid4

from django.db.models import Count
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Booking, Conversation, Diagnosis, MediaUpload, Message
from .serializers import (
    BookingRequestSerializer,
    BookingSerializer,
    ChatRequestSerializer,
    ConversationSummarySerializer,
    DiagnosisRequestSerializer,
    DiagnosisSerializer,
    MediaUploadSerializer,
    MessageSerializer,
    UploadRequestSerializer,
)
from .services import diagnosis_engine, gemini_client, media_validator, rule_engine


@api_view(['GET'])
def health_check(request):
    """Server zinda hai ya nahi — deployment ke baad test karne ke liye."""
    return Response({'status': 'ok', 'service': 'ai-car-mechanic-backend'})


def _get_conversation_or_error(conversation_id):
    """Conversation dhoondhta hai. Returns (conversation, error_response).

    - conversation_id None  -> (None, None)   # caller nayi conversation banaye
    - mil gayi              -> (conversation, None)
    - nahi mili             -> (None, 404 Response)
    - closed hai            -> (None, 400 Response)
    """
    if conversation_id is None:
        return None, None
    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return None, Response(
            {'detail': f'Conversation {conversation_id} not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    if conversation.status == Conversation.Status.CLOSED:
        return None, Response(
            {'detail': 'This conversation is closed. Please start a new one.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return conversation, None


@api_view(['GET'])
def conversation_list(request):
    """GET /api/conversations/ — history sidebar ke liye saari conversations.

    annotate(message_count=...) ek hi query mein har conversation ka message
    count le aata hai (N+1 queries se bachne ka standard Django tarika).
    order_by('-updated_at') zaroori hai: annotate() ke baad Django Meta.ordering
    drop kar deta hai, warna rows random order mein aati hain.
    """
    conversations = Conversation.objects.annotate(
        message_count=Count('messages')
    ).order_by('-updated_at')
    return Response(
        {'conversations': ConversationSummarySerializer(conversations, many=True).data}
    )


@api_view(['GET'])
def conversation_detail(request, conversation_id):
    """GET /api/conversations/<id>/ — purani conversation ki poori history.

    Chat UI isse restore karta hai: messages + media (timeline ke liye),
    latest diagnosis aur uski booking (agar hui ho).
    """
    try:
        conversation = Conversation.objects.annotate(
            message_count=Count('messages')
        ).get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return Response(
            {'detail': f'Conversation {conversation_id} not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    messages = conversation.messages.all()  # Meta ordering: created_at
    media = conversation.media_uploads.order_by('created_at')
    diagnosis = conversation.diagnoses.first()  # Meta ordering: -created_at = latest
    booking = (
        Booking.objects.filter(diagnosis__conversation=conversation)
        .order_by('-created_at')
        .first()
    )

    return Response(
        {
            'conversation': ConversationSummarySerializer(conversation).data,
            'messages': MessageSerializer(messages, many=True).data,
            # context={'request': request} — file URL absolute banane ke liye
            # (warna frontend ko relative "/media/..." milega).
            'media': MediaUploadSerializer(
                media, many=True, context={'request': request}
            ).data,
            'diagnosis': DiagnosisSerializer(diagnosis).data if diagnosis else None,
            'booking': BookingSerializer(booking).data if booking else None,
        }
    )


@api_view(['POST'])
def chat(request):
    """POST /api/chat/ — user ka message save karo aur bot ka reply return karo."""
    serializer = ChatRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    conversation_id = data.get('conversation_id')
    is_new_conversation = conversation_id is None

    conversation, error_response = _get_conversation_or_error(conversation_id)
    if error_response is not None:
        return error_response
    if is_new_conversation:
        conversation = Conversation.objects.create(title=data['message'][:60])

    user_message = Message.objects.create(
        conversation=conversation,
        role=Message.Role.USER,
        content=data['message'],
        generated_by=Message.GeneratedBy.USER,
    )

    reply_data = rule_engine.generate_reply(conversation, user_message)

    if reply_data.get('needs_nlu'):
        # Rule engine ko ye message samajh nahi aaya — Gemini se ek natural
        # follow-up sawaal maango. Fail ho (None) to rule ka reply hi chalega.
        ai_reply = gemini_client.chat_reply(conversation)
        if ai_reply is not None:
            reply_data = ai_reply

    reply_message = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=reply_data['content'],
        generated_by=reply_data['generated_by'],
    )

    conversation.save()

    body = {
        'conversation_id': conversation.pk,
        'conversation_title': conversation.title,
        'user_message': MessageSerializer(user_message).data,
        'reply': MessageSerializer(reply_message).data,
    }
    http_status = status.HTTP_201_CREATED if is_new_conversation else status.HTTP_200_OK
    return Response(body, status=http_status)


@api_view(['POST'])
def upload_media(request):
    """POST /api/upload/ — image/audio/video file validate karke save karo."""
    serializer = UploadRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    uploaded_file = data['file']

    try:
        media_type, mime_type = media_validator.validate_and_classify(uploaded_file)
    except media_validator.MediaValidationError as exc:
        return Response(
            {'file': [str(exc)]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    conversation_id = data.get('conversation_id')
    is_new_conversation = conversation_id is None

    conversation, error_response = _get_conversation_or_error(conversation_id)
    if error_response is not None:
        return error_response
    if is_new_conversation:
        conversation = Conversation.objects.create(
            title=f'Upload: {uploaded_file.name[:50]}'
        )

    media = MediaUpload.objects.create(
        conversation=conversation,
        file=uploaded_file,
        media_type=media_type,
        original_name=uploaded_file.name,
        size_bytes=uploaded_file.size,
        mime_type=mime_type,
    )

    conversation.save()

    body = {
        'conversation_id': conversation.pk,
        'conversation_title': conversation.title,
        'media': MediaUploadSerializer(media, context={'request': request}).data,
    }
    http_status = status.HTTP_201_CREATED if is_new_conversation else status.HTTP_200_OK
    return Response(body, status=http_status)


@api_view(['POST'])
def diagnosis(request):
    """POST /api/diagnosis/ — conversation se structured diagnosis banao."""
    serializer = DiagnosisRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    conversation, error_response = _get_conversation_or_error(data['conversation_id'])
    if error_response is not None:
        return error_response

    if not conversation.messages.filter(role=Message.Role.USER).exists():
        return Response(
            {
                'detail': (
                    'No user messages in this conversation yet. '
                    'Please describe the problem in chat first.'
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    diagnosis_data = diagnosis_engine.generate_diagnosis(conversation)

    if diagnosis_data['needs_nlu']:
        # Rule engine ne haath khade kar diye — ab Gemini ko ek chance do.
        # Fail ho jaye (None) to rule engine ka honest fallback hi chalega.
        ai_diagnosis = gemini_client.diagnose(conversation)
        if ai_diagnosis is not None:
            diagnosis_data = ai_diagnosis

    diagnosis_record = Diagnosis.objects.create(
        conversation=conversation,
        summary=diagnosis_data['summary'],
        likely_issue=diagnosis_data['likely_issue'],
        reasoning=diagnosis_data['reasoning'],
        confidence=diagnosis_data['confidence'],
        can_drive=diagnosis_data['can_drive'],
        next_step=diagnosis_data['next_step'],
        recommended_service=diagnosis_data['recommended_service'],
        generated_by=diagnosis_data['generated_by'],
    )

    conversation.status = Conversation.Status.DIAGNOSED
    conversation.save()

    body = {
        'conversation_id': conversation.pk,
        'conversation_status': conversation.status,
        'diagnosis': DiagnosisSerializer(diagnosis_record).data,
    }
    return Response(body, status=status.HTTP_201_CREATED)


def _generate_booking_ref():
    """Unique booking reference banata hai — jaise BK-4F8A2C1D."""
    while True:
        ref = f'BK-{uuid4().hex[:8].upper()}'
        if not Booking.objects.filter(booking_ref=ref).exists():
            return ref


@api_view(['POST'])
def booking(request):
    """POST /api/booking/ — diagnosis ke liye mechanic appointment banao."""
    serializer = BookingRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        diagnosis_record = Diagnosis.objects.get(pk=data['diagnosis_id'])
    except Diagnosis.DoesNotExist:
        return Response(
            {'detail': f'Diagnosis {data["diagnosis_id"]} not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if Booking.objects.filter(diagnosis=diagnosis_record).exists():
        return Response(
            {'detail': 'A booking already exists for this diagnosis.'},
            status=status.HTTP_409_CONFLICT,
        )

    booking_record = Booking.objects.create(
        booking_ref=_generate_booking_ref(),
        diagnosis=diagnosis_record,
        customer_name=data['customer_name'],
        phone=data['phone'],
        preferred_date=data['preferred_date'],
    )

    conversation = diagnosis_record.conversation
    conversation.status = Conversation.Status.BOOKED
    conversation.save()

    body = {
        'conversation_id': conversation.pk,
        'conversation_status': conversation.status,
        'booking': BookingSerializer(booking_record).data,
    }
    return Response(body, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def booking_detail(request, booking_id):
    """GET /api/booking/<id>/ — ek booking ka current status dekho."""
    try:
        booking_record = Booking.objects.get(pk=booking_id)
    except Booking.DoesNotExist:
        return Response(
            {'detail': f'Booking {booking_id} not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({'booking': BookingSerializer(booking_record).data})
