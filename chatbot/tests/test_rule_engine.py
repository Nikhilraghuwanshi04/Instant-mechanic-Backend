"""Rule engine (chat ka dimaag) ke unit tests.

Ye 100% offline hain — koi Gemini call nahi hoti. Har test ek asli user
phrase se engine ko challenge karta hai aur reply ka exact behaviour
check karta hai (safety priority, sawaal-poochhna, needs_nlu handoff).
"""

from django.test import TestCase

from ..models import Conversation, Message
from ..services import knowledge_base as kb
from ..services.rule_engine import generate_reply


class RuleEngineTests(TestCase):
    """generate_reply() ka behaviour — conversation + user message ke saath."""

    def _exchange(self, conversation, text):
        """Ek poora chat turn — bilkul jaise view karta hai.

        user message save → generate_reply → assistant reply save.
        (Reply ko save karna zaroori hai: agle turn ka follow-up logic
        purane replies ke text se hi yaad rakhta hai kya poochha ja chuka.)
        """
        user_message = Message.objects.create(
            conversation=conversation, role=Message.Role.USER, content=text
        )
        reply = generate_reply(conversation, user_message)
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=reply['content'],
            generated_by=reply['generated_by'],
        )
        return reply

    # ---- Safety pehle ----

    def test_safety_beats_symptoms(self):
        conversation = Conversation.objects.create()
        reply = self._exchange(
            conversation, 'Smoke is coming from the engine and the brakes grind.'
        )
        self.assertIn('Smoke is a red flag', reply['content'])
        self.assertNotIn('Brakes are your number one safety system', reply['content'])
        self.assertEqual(reply['generated_by'], Message.GeneratedBy.RULE_ENGINE)
        self.assertFalse(reply['needs_nlu'])

    def test_fire_is_top_safety(self):
        conversation = Conversation.objects.create()
        reply = self._exchange(conversation, 'My car is on fire!')
        self.assertIn('Stop driving now', reply['content'])

    # ---- Symptom flow ----

    def test_brake_squeal_gets_explanation_and_first_question(self):
        conversation = Conversation.objects.create()
        reply = self._exchange(conversation, 'My car squeals every time I brake.')
        self.assertIn('Brakes are your number one safety system', reply['content'])
        self.assertIn('When do you notice it', reply['content'])
        self.assertFalse(reply['needs_nlu'])

    def test_repeat_symptom_gets_short_ack_and_next_question(self):
        conversation = Conversation.objects.create()
        self._exchange(conversation, 'My car squeals every time I brake.')
        reply = self._exchange(conversation, 'It also happens when I brake gently.')
        self.assertIn('Got it — noted.', reply['content'])
        self.assertIn('Roughly how long has this been happening', reply['content'])
        self.assertNotIn('Brakes are your number one safety system', reply['content'])

    def test_all_questions_asked_ready_for_diagnosis(self):
        conversation = Conversation.objects.create()
        self._exchange(conversation, 'My car squeals every time I brake.')
        self._exchange(conversation, 'It happens every time I press the pedal.')
        reply = self._exchange(conversation, 'The grinding started about a week ago.')
        self.assertIn(kb.READY_FOR_DIAGNOSIS, reply['content'])

    def test_followup_without_keywords_uses_context(self):
        conversation = Conversation.objects.create()
        self._exchange(conversation, 'My car squeals every time I brake.')
        reply = self._exchange(conversation, 'It has been going on for two weeks now.')
        self.assertIn('Noted, thanks — that helps.', reply['content'])
        self.assertIn('Roughly how long has this been happening', reply['content'])

    def test_two_symptoms_in_one_message(self):
        conversation = Conversation.objects.create()
        reply = self._exchange(
            conversation, 'My car squeals when braking and the engine rattles.'
        )
        self.assertIn('Brakes are your number one safety system', reply['content'])
        self.assertIn('Engine noises and vibration', reply['content'])

    # ---- Topic handling ----

    def test_greeting(self):
        conversation = Conversation.objects.create()
        reply = self._exchange(conversation, 'hello')
        self.assertEqual(reply['content'], kb.GREETING_REPLY)

    def test_greeting_prefix_on_symptom(self):
        conversation = Conversation.objects.create()
        reply = self._exchange(conversation, "Hi, my car won't start in the morning.")
        self.assertTrue(reply['content'].startswith('Hello! '))
        self.assertIn('battery', reply['content'].lower())

    def test_thanks(self):
        conversation = Conversation.objects.create()
        reply = self._exchange(conversation, 'thanks!')
        self.assertEqual(reply['content'], kb.THANKS_REPLY)

    def test_off_topic_is_politely_rejected(self):
        conversation = Conversation.objects.create()
        reply = self._exchange(conversation, 'What is the capital of France?')
        self.assertEqual(reply['content'], kb.OFF_TOPIC_REPLY)

    def test_help_question(self):
        conversation = Conversation.objects.create()
        reply = self._exchange(conversation, 'What can you do?')
        self.assertEqual(reply['content'], kb.HELP_REPLY)

    def test_vague_message_gets_guiding_question(self):
        conversation = Conversation.objects.create()
        reply = self._exchange(conversation, 'There is a strange noise.')
        self.assertEqual(reply['content'], kb.VAGUE_REPLY)

    def test_car_mentioned_but_unclear_sets_needs_nlu(self):
        conversation = Conversation.objects.create()
        reply = self._exchange(conversation, 'My car feels a bit off today.')
        self.assertEqual(reply['content'], kb.CAR_UNCLEAR_REPLY)
        self.assertTrue(reply['needs_nlu'])
        self.assertEqual(reply['generated_by'], Message.GeneratedBy.RULE_ENGINE)
