"""Health, conversation list aur conversation detail ke integration tests.

History sidebar ka data-shape yahan verify hota hai: ordering (newest
pehle), message_count (annotate se — N+1 query nahi), last_message_preview
(80 chars + ellipsis), aur conversation detail ka poora timeline
(messages + media + diagnosis + booking).
"""

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from ..models import Booking, Conversation, Message
from .helpers import ApiTestCase


@override_settings(GEMINI_API_KEY='')
class HealthEndpointTests(ApiTestCase):
    def test_health_returns_ok(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data, {'status': 'ok', 'service': 'ai-car-mechanic-backend'}
        )


@override_settings(GEMINI_API_KEY='')
class ConversationListTests(ApiTestCase):
    URL = '/api/conversations/'

    def test_list_ordered_by_updated_at_with_counts_and_preview(self):
        older = self.make_conversation(
            'My brakes squeal.', 'It happens when braking.', title='Older'
        )
        self.make_conversation('x' * 100, title='Newer')

        # updated_at pe auto_now laga hai — direct .update() hi use bypass karta
        # hai (save() nahi), isliye ordering test deterministic ban jata hai.
        Conversation.objects.filter(pk=older.pk).update(
            updated_at=timezone.now() - timedelta(days=1)
        )

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)
        conversations = response.data['conversations']
        self.assertEqual([c['title'] for c in conversations], ['Newer', 'Older'])
        self.assertEqual(conversations[0]['message_count'], 1)
        self.assertEqual(conversations[1]['message_count'], 2)
        # 100 chars > 80, isliye preview 80 chars + '…' (U+2026) hai.
        self.assertEqual(conversations[0]['last_message_preview'], 'x' * 80 + '…')
        self.assertEqual(
            conversations[1]['last_message_preview'], 'It happens when braking.'
        )

    def test_list_preview_is_none_for_empty_conversation(self):
        self.make_conversation(title='No messages yet')
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        conversation = response.data['conversations'][0]
        self.assertIsNone(conversation['last_message_preview'])
        self.assertEqual(conversation['message_count'], 0)


@override_settings(GEMINI_API_KEY='')
class ConversationDetailTests(ApiTestCase):
    def test_detail_returns_full_timeline(self):
        conversation = self.make_conversation('My brakes squeal.')
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content='Brakes are your number one safety system...',
            generated_by=Message.GeneratedBy.RULE_ENGINE,
        )
        diagnosis = self.make_diagnosis(conversation)
        booking = Booking.objects.create(
            booking_ref='BK-FEED0001',
            diagnosis=diagnosis,
            customer_name='Asha Verma',
            phone='+91 98765 43210',
            preferred_date=timezone.localdate() + timedelta(days=3),
        )

        response = self.client.get(f'/api/conversations/{conversation.id}/')

        self.assertEqual(response.status_code, 200)
        body = response.data
        self.assertEqual(body['conversation']['id'], conversation.id)
        self.assertEqual(body['conversation']['message_count'], 2)
        self.assertEqual([m['role'] for m in body['messages']], ['user', 'assistant'])
        self.assertEqual(body['media'], [])
        self.assertEqual(body['diagnosis']['id'], diagnosis.id)
        self.assertEqual(body['diagnosis']['likely_issue'], diagnosis.likely_issue)
        self.assertEqual(body['booking']['booking_ref'], booking.booking_ref)

    def test_detail_without_diagnosis_returns_nulls(self):
        conversation = self.make_conversation('Just chatting.')
        response = self.client.get(f'/api/conversations/{conversation.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['diagnosis'])
        self.assertIsNone(response.data['booking'])
        self.assertEqual(response.data['messages'][0]['content'], 'Just chatting.')

    def test_detail_missing_returns_404(self):
        response = self.client.get('/api/conversations/999999/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'Conversation 999999 not found.')
