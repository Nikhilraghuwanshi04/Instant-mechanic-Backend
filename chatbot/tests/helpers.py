"""API tests ke liye shared helpers — asli HTTP jaisa safar, network ke bina.

`APITestCase` DRF ka test client deta hai jo request ko poore URL routing +
view + serializer stack se guzarta hai (in-memory — koi asli socket nahi).
Matlab test bilkul wahi darwaza khatkhatata hai jo browser khatkhatata hai.

`helpers.py` naam jaan-boojh kar `test_` se shuru NAHI hota — Django test
runner sirf `test*.py` files ko discover karta hai, isliye ye file (jo tests
nahi, tools rakhti hai) suite mein count nahi hoti.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from ..models import Conversation, Diagnosis, Message

# Chhota PNG sample (asli magic bytes + padding) — upload API tests ke liye.
PNG_BYTES = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


def png_file(name='photo.png'):
    """Valid PNG jaisi in-memory upload file."""
    return SimpleUploadedFile(name, PNG_BYTES, content_type='image/png')


class ApiTestCase(APITestCase):
    """Base class — chhote helpers taaki har test sirf apni baat pe focus kare."""

    def make_conversation(self, *user_texts, title='Test conversation'):
        conversation = Conversation.objects.create(title=title)
        for text in user_texts:
            Message.objects.create(
                conversation=conversation, role=Message.Role.USER, content=text
            )
        return conversation

    def make_diagnosis(self, conversation, **overrides):
        fields = {
            'conversation': conversation,
            'summary': {
                'primary_symptom': {'id': 'brakes', 'label': 'Brake system'},
                'matched_terms': ['brakes', 'squealing'],
                'secondary_symptoms': [],
                'safety_flags': [],
            },
            'likely_issue': 'Worn brake pads or a brake system fault',
            'reasoning': (
                'Brake noise and pedal changes typically come from worn '
                'pads, warped discs, or low brake fluid.'
            ),
            'confidence': Diagnosis.Confidence.MEDIUM,
            'can_drive': False,
            'next_step': 'Avoid long drives until a mechanic inspects the brakes.',
            'recommended_service': 'Brake inspection (pads, discs, fluid)',
            'generated_by': Diagnosis.GeneratedBy.RULE_ENGINE,
        }
        fields.update(overrides)
        return Diagnosis.objects.create(**fields)
