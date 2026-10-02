"""POST /api/chat/ ke integration tests — poora HTTP stack (URL → view → DB).

Har test mein Gemini OFF hai (@override_settings se key khaali) taaki suite
kabhi internet pe depend na kare. Gemini ke ON wale raste alag mock tests
mein hain — wahan generate_text ko patch karke fake jawab bhejte hain.
"""

from unittest.mock import patch

from django.test import override_settings

from ..models import Conversation, Message
from ..services import knowledge_base as kb
from .helpers import ApiTestCase


@override_settings(GEMINI_API_KEY='')
class ChatEndpointTests(ApiTestCase):
    URL = '/api/chat/'

    def test_new_conversation_returns_201_and_saves_both_messages(self):
        response = self.client.post(
            self.URL, {'message': 'My brakes squeal when I stop.'}, format='json'
        )

        self.assertEqual(response.status_code, 201)
        body = response.data
        self.assertEqual(body['conversation_title'], 'My brakes squeal when I stop.')
        self.assertEqual(body['user_message']['role'], 'user')
        self.assertEqual(body['reply']['role'], 'assistant')
        self.assertEqual(body['reply']['generated_by'], 'rule_engine')
        self.assertIn('worn pads', body['reply']['content'])

        conversation = Conversation.objects.get(pk=body['conversation_id'])
        self.assertEqual(conversation.messages.count(), 2)

    def test_existing_conversation_returns_200_and_keeps_title(self):
        conversation = self.make_conversation(
            'My brakes squeal when I stop.', title='Brake trouble'
        )
        response = self.client.post(
            self.URL,
            {
                'message': 'It has been going on for two weeks now.',
                'conversation_id': conversation.id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['conversation_id'], conversation.id)
        self.assertEqual(response.data['conversation_title'], 'Brake trouble')
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertIn('Noted, thanks', response.data['reply']['content'])

    def test_missing_conversation_returns_404(self):
        response = self.client.post(
            self.URL,
            {'message': 'Hello', 'conversation_id': 999999},
            format='json',
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'Conversation 999999 not found.')

    def test_closed_conversation_returns_400(self):
        conversation = self.make_conversation()
        conversation.status = Conversation.Status.CLOSED
        conversation.save()
        response = self.client.post(
            self.URL,
            {'message': 'Hello', 'conversation_id': conversation.id},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['detail'],
            'This conversation is closed. Please start a new one.',
        )

    def test_empty_message_returns_400(self):
        response = self.client.post(self.URL, {'message': '   '}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['message'][0], 'Message cannot be empty.')

    def test_missing_message_returns_400(self):
        response = self.client.post(self.URL, {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['message'][0], 'Message is required.')

    def test_message_too_long_returns_400(self):
        response = self.client.post(self.URL, {'message': 'a' * 2001}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['message'][0],
            'Message is too long (max 2000 characters).',
        )

    def test_message_at_max_length_is_accepted(self):
        response = self.client.post(self.URL, {'message': 'a' * 2000}, format='json')
        self.assertEqual(response.status_code, 201)

    def test_invalid_conversation_id_returns_400(self):
        response = self.client.post(
            self.URL,
            {'message': 'Hello', 'conversation_id': 0},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['conversation_id'][0],
            'conversation_id must be a positive integer.',
        )

    def test_get_method_not_allowed(self):
        self.assertEqual(self.client.get(self.URL).status_code, 405)

    def test_safety_priority_over_symptoms(self):
        response = self.client.post(
            self.URL,
            {'message': 'Smoke is coming from the engine and the brakes grind.'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('Smoke is a red flag', response.data['reply']['content'])
        self.assertNotIn('worn pads', response.data['reply']['content'])


class GeminiChatFallbackTests(ApiTestCase):
    """needs_nlu wala rasta — Gemini mocked, internet ki zaroorat ZERO.

    Dono outcomes test hote hain: (1) Gemini jawab de to uski reply jaati
    hai, (2) Gemini fail ho to rule engine ka honest reply hi chalta hai.
    """

    URL = '/api/chat/'
    UNCLEAR_MESSAGE = 'My car feels a bit off today.'  # car mention, koi symptom nahi

    @patch('chatbot.services.gemini_client.generate_text')
    def test_gemini_reply_wins_when_available(self, mock_generate_text):
        mock_generate_text.return_value = (
            'Got it — when exactly does the car feel off, and does it happen '
            'at idle or while driving?',
            'gemini-test-model',
        )
        response = self.client.post(
            self.URL, {'message': self.UNCLEAR_MESSAGE}, format='json'
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['reply']['generated_by'], 'gemini')
        self.assertIn('when exactly', response.data['reply']['content'])
        mock_generate_text.assert_called_once()

        conversation = Conversation.objects.get(pk=response.data['conversation_id'])
        self.assertEqual(
            conversation.messages.last().generated_by, Message.GeneratedBy.GEMINI
        )

    @patch('chatbot.services.gemini_client.generate_text')
    def test_rule_reply_kept_when_gemini_fails(self, mock_generate_text):
        mock_generate_text.return_value = (None, None)
        response = self.client.post(
            self.URL, {'message': self.UNCLEAR_MESSAGE}, format='json'
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['reply']['generated_by'], 'rule_engine')
        self.assertEqual(response.data['reply']['content'], kb.CAR_UNCLEAR_REPLY)
