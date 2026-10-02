"""POST /api/diagnosis/ ke integration tests — rules + Gemini fallback.

Gemini OFF (key khaali) wale tests rule engine ka poora rasta cover karte
hain. Gemini fallback tests mein generate_text mocked hai — fake JSON
bhejkar dono outcomes check hote hain: valid JSON mila to gemini wali
diagnosis save hoti hai, malformed mila to rule engine ka honest answer
hi chalta hai (user ko kabhi error nahi).
"""

import json
from unittest.mock import patch

from django.test import override_settings

from ..models import Conversation, Message
from .helpers import ApiTestCase


@override_settings(GEMINI_API_KEY='')
class DiagnosisEndpointTests(ApiTestCase):
    URL = '/api/diagnosis/'

    def test_rule_diagnosis_created_201(self):
        conversation = self.make_conversation(
            'The brakes squeal and grind when I press the pedal hard.'
        )
        response = self.client.post(
            self.URL, {'conversation_id': conversation.id}, format='json'
        )

        self.assertEqual(response.status_code, 201)
        body = response.data
        self.assertEqual(body['conversation_status'], 'diagnosed')

        diagnosis = body['diagnosis']
        self.assertEqual(diagnosis['generated_by'], 'rule_engine')
        self.assertEqual(diagnosis['confidence'], 'high')
        self.assertFalse(diagnosis['can_drive'])
        self.assertEqual(
            diagnosis['likely_issue'], 'Worn brake pads or a brake system fault'
        )
        self.assertEqual(diagnosis['summary']['primary_symptom']['id'], 'brakes')
        self.assertEqual(diagnosis['summary']['user_messages_analyzed'], 1)
        self.assertEqual(conversation.diagnoses.count(), 1)

        conversation.refresh_from_db()
        self.assertEqual(conversation.status, Conversation.Status.DIAGNOSED)

    def test_needs_nlu_without_gemini_still_creates_201(self):
        conversation = self.make_conversation(
            'The flux capacitor hums oddly at midnight.'  # koi symptom match nahi
        )
        response = self.client.post(
            self.URL, {'conversation_id': conversation.id}, format='json'
        )

        self.assertEqual(response.status_code, 201)
        diagnosis = response.data['diagnosis']
        self.assertEqual(diagnosis['generated_by'], 'rule_engine')
        self.assertEqual(
            diagnosis['likely_issue'],
            'Insufficient information for a rule-based diagnosis',
        )

    def test_no_user_messages_returns_400(self):
        conversation = Conversation.objects.create(title='Empty')
        response = self.client.post(
            self.URL, {'conversation_id': conversation.id}, format='json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['detail'],
            'No user messages in this conversation yet. '
            'Please describe the problem in chat first.',
        )

    def test_missing_conversation_returns_404(self):
        response = self.client.post(
            self.URL, {'conversation_id': 999999}, format='json'
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'Conversation 999999 not found.')

    def test_missing_conversation_id_returns_400(self):
        response = self.client.post(self.URL, {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['conversation_id'][0],
            'conversation_id is required for a diagnosis.',
        )

    def test_get_method_not_allowed(self):
        self.assertEqual(self.client.get(self.URL).status_code, 405)


class GeminiDiagnosisFallbackTests(ApiTestCase):
    """needs_nlu wala diagnosis rasta — Gemini mocked, internet ki zaroorat ZERO.

    Dono outcomes test hote hain: (1) Gemini valid JSON de to uski diagnosis
    save hoti hai, (2) Gemini ka jawab malformed ho to rule engine ka
    conservative fallback hi chalta hai.
    """

    URL = '/api/diagnosis/'
    FUZZY_MESSAGE = 'The flux capacitor hums oddly at midnight.'

    @patch('chatbot.services.gemini_client.generate_text')
    def test_gemini_json_diagnosis_used_when_rules_fail(self, mock_generate_text):
        mock_generate_text.return_value = (
            json.dumps(
                {
                    'likely_issue': 'Possible sensor or ECU glitch',
                    'reasoning': (
                        'The described behaviour does not match a known '
                        'mechanical pattern.'
                    ),
                    'confidence': 'low',
                    'can_drive': False,
                    'next_step': 'Have a workshop run a full diagnostic scan.',
                    'recommended_service': 'Computer diagnostics (OBD scan)',
                }
            ),
            'gemini-test-model',
        )
        conversation = self.make_conversation(self.FUZZY_MESSAGE)

        response = self.client.post(
            self.URL, {'conversation_id': conversation.id}, format='json'
        )

        self.assertEqual(response.status_code, 201)
        diagnosis = response.data['diagnosis']
        self.assertEqual(diagnosis['generated_by'], 'gemini')
        self.assertEqual(diagnosis['likely_issue'], 'Possible sensor or ECU glitch')
        self.assertFalse(diagnosis['can_drive'])
        self.assertEqual(diagnosis['summary']['source'], 'gemini')
        self.assertEqual(diagnosis['summary']['model'], 'gemini-test-model')

        mock_generate_text.assert_called_once()
        self.assertIs(mock_generate_text.call_args.kwargs.get('json_mode'), True)

    @patch('chatbot.services.gemini_client.generate_text')
    def test_malformed_gemini_json_falls_back_to_rule(self, mock_generate_text):
        mock_generate_text.return_value = (
            'Sorry, I cannot answer in JSON.',
            'gemini-test-model',
        )
        conversation = self.make_conversation(self.FUZZY_MESSAGE)

        response = self.client.post(
            self.URL, {'conversation_id': conversation.id}, format='json'
        )

        self.assertEqual(response.status_code, 201)
        diagnosis = response.data['diagnosis']
        self.assertEqual(diagnosis['generated_by'], 'rule_engine')
        self.assertEqual(
            diagnosis['likely_issue'],
            'Insufficient information for a rule-based diagnosis',
        )
