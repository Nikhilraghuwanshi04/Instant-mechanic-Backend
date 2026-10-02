"""Diagnosis engine ke unit tests — conversation history se structured diagnosis.

Yahan bhi sab kuch offline hai: sirf rule-engine logic test hota hai
(confidence levels, can_drive ka safety rule, KB priority order,
aur needs_nlu handoff jo Gemini ko signal deta hai).
"""

from django.test import TestCase

from ..models import Conversation, Diagnosis, Message
from ..services import knowledge_base as kb
from ..services.diagnosis_engine import generate_diagnosis


class DiagnosisEngineTests(TestCase):
    """generate_diagnosis() ke rules — evidence in, structured dict out."""

    def _conversation_with(self, *texts):
        """Ek conversation jisme diye gaye user messages pehle se hain."""
        conversation = Conversation.objects.create(title='Test conversation')
        for text in texts:
            Message.objects.create(
                conversation=conversation, role=Message.Role.USER, content=text
            )
        return conversation

    def test_single_term_is_low_confidence(self):
        conversation = self._conversation_with('The AC is weak.')
        result = generate_diagnosis(conversation)
        self.assertEqual(result['confidence'], Diagnosis.Confidence.LOW)
        self.assertTrue(result['can_drive'])
        self.assertFalse(result['needs_nlu'])
        self.assertEqual(result['generated_by'], Diagnosis.GeneratedBy.RULE_ENGINE)
        self.assertEqual(
            result['recommended_service'],
            kb.get_category('ac')['recommended_service'],
        )

    def test_two_terms_is_medium_confidence(self):
        conversation = self._conversation_with('My car squeals every time I brake.')
        result = generate_diagnosis(conversation)
        self.assertEqual(result['confidence'], Diagnosis.Confidence.MEDIUM)
        self.assertFalse(result['can_drive'])
        self.assertEqual(
            result['likely_issue'], 'Worn brake pads or a brake system fault'
        )

    def test_three_plus_terms_is_high_confidence(self):
        conversation = self._conversation_with(
            'The brakes squeal and grind when I press the pedal hard.'
        )
        result = generate_diagnosis(conversation)
        self.assertEqual(result['confidence'], Diagnosis.Confidence.HIGH)

    def test_multiple_messages_accumulate_evidence(self):
        conversation = self._conversation_with(
            'My steering wobbles at high speed.',
            'It also pulls to the right.',
        )
        result = generate_diagnosis(conversation)
        self.assertEqual(result['summary']['user_messages_analyzed'], 2)
        self.assertEqual(
            result['summary']['primary_symptom']['id'], 'steering_suspension'
        )
        self.assertEqual(result['confidence'], Diagnosis.Confidence.HIGH)
        self.assertTrue(result['can_drive'])

    def test_kb_order_decides_primary_symptom(self):
        conversation = self._conversation_with(
            "My car won't start and the brakes grind."
        )
        result = generate_diagnosis(conversation)
        self.assertEqual(result['summary']['primary_symptom']['id'], 'brakes')
        self.assertEqual(
            result['summary']['secondary_symptoms'][0]['id'], 'battery_electrical'
        )
        self.assertFalse(result['can_drive'])
        self.assertIn(
            'The conversation also mentions issues in: Battery and electrical',
            result['reasoning'],
        )

    def test_can_drive_requires_every_detected_category_safe(self):
        conversation = self._conversation_with(
            'The steering wobbles and the brakes grind badly.'
        )
        result = generate_diagnosis(conversation)
        self.assertFalse(result['can_drive'])

    def test_safety_flag_forces_can_drive_false_and_leads_next_step(self):
        conversation = self._conversation_with(
            "The engine is overheating and there's steam from the bonnet."
        )
        result = generate_diagnosis(conversation)
        self.assertFalse(result['can_drive'])
        flag = result['summary']['safety_flags'][0]
        self.assertIn('Steam from the bonnet', flag)
        self.assertTrue(result['next_step'].startswith(flag))
        self.assertIn('safety-critical', result['reasoning'])

    def test_no_match_returns_honest_needs_nlu(self):
        conversation = self._conversation_with(
            'The flux capacitor hums oddly at midnight.'
        )
        result = generate_diagnosis(conversation)
        self.assertTrue(result['needs_nlu'])
        self.assertFalse(result['can_drive'])
        self.assertEqual(result['confidence'], Diagnosis.Confidence.LOW)
        self.assertEqual(result['recommended_service'], 'General inspection')
        self.assertEqual(
            result['likely_issue'],
            'Insufficient information for a rule-based diagnosis',
        )

    def test_safety_alone_still_conservative(self):
        conversation = self._conversation_with('I smell smoke.')
        result = generate_diagnosis(conversation)
        self.assertTrue(result['needs_nlu'])
        self.assertFalse(result['can_drive'])
        self.assertEqual(len(result['summary']['safety_flags']), 1)

    def test_summary_records_match_evidence(self):
        conversation = self._conversation_with('My car squeals every time I brake.')
        result = generate_diagnosis(conversation)
        summary = result['summary']
        self.assertEqual(summary['user_messages_analyzed'], 1)
        self.assertEqual(summary['primary_symptom']['id'], 'brakes')
        self.assertIn('brakes', summary['matched_terms'])
        self.assertIn('squealing', summary['matched_terms'])
        self.assertEqual(summary['secondary_symptoms'], [])
        self.assertEqual(summary['safety_flags'], [])
