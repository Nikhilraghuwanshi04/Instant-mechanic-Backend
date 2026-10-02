"""POST /api/booking/ + GET /api/booking/<id>/ ke integration tests.

Booking flow ka poora error matrix: validation (past date, galat phone),
missing diagnosis (404), duplicate booking (409) — aur booking banne pe
conversation ka status 'booked' ho jata hai.
"""

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from ..models import Booking, Conversation
from .helpers import ApiTestCase


def _date_in(days):
    """Aaj se X din aage/peeche ki date — ISO string (form input jaisi)."""
    return (timezone.localdate() + timedelta(days=days)).isoformat()


@override_settings(GEMINI_API_KEY='')
class BookingEndpointTests(ApiTestCase):
    URL = '/api/booking/'

    def _payload(self, diagnosis, **overrides):
        payload = {
            'diagnosis_id': diagnosis.id,
            'customer_name': 'Asha Verma',
            'phone': '+91 98765 43210',
            'preferred_date': _date_in(1),
        }
        payload.update(overrides)
        return payload

    def test_create_booking_returns_201_and_marks_conversation_booked(self):
        conversation = self.make_conversation('My brakes squeal.')
        diagnosis = self.make_diagnosis(conversation)

        response = self.client.post(self.URL, self._payload(diagnosis), format='json')

        self.assertEqual(response.status_code, 201)
        body = response.data
        self.assertEqual(body['conversation_status'], 'booked')

        booking = body['booking']
        self.assertTrue(booking['booking_ref'].startswith('BK-'))
        self.assertEqual(booking['diagnosis_id'], diagnosis.id)
        self.assertEqual(booking['conversation_id'], conversation.id)
        self.assertEqual(booking['likely_issue'], diagnosis.likely_issue)
        self.assertEqual(booking['customer_name'], 'Asha Verma')
        self.assertEqual(booking['status'], 'pending')

        conversation.refresh_from_db()
        self.assertEqual(conversation.status, Conversation.Status.BOOKED)

    def test_past_date_returns_400(self):
        conversation = self.make_conversation('My brakes squeal.')
        diagnosis = self.make_diagnosis(conversation)
        response = self.client.post(
            self.URL,
            self._payload(diagnosis, preferred_date=_date_in(-1)),
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['preferred_date'][0],
            'Preferred date cannot be in the past.',
        )

    def test_invalid_phone_returns_400(self):
        conversation = self.make_conversation('My brakes squeal.')
        diagnosis = self.make_diagnosis(conversation)
        response = self.client.post(
            self.URL, self._payload(diagnosis, phone='not-a-phone'), format='json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['phone'][0], 'Enter a valid phone number.')

    def test_missing_diagnosis_returns_404(self):
        response = self.client.post(
            self.URL,
            {
                'diagnosis_id': 999999,
                'customer_name': 'Asha Verma',
                'phone': '+91 98765 43210',
                'preferred_date': _date_in(1),
            },
            format='json',
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'Diagnosis 999999 not found.')

    def test_duplicate_booking_returns_409(self):
        conversation = self.make_conversation('My brakes squeal.')
        diagnosis = self.make_diagnosis(conversation)
        Booking.objects.create(
            booking_ref='BK-TEST0001',
            diagnosis=diagnosis,
            customer_name='Asha Verma',
            phone='+91 98765 43210',
            preferred_date=timezone.localdate() + timedelta(days=1),
        )

        response = self.client.post(self.URL, self._payload(diagnosis), format='json')

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data['detail'],
            'A booking already exists for this diagnosis.',
        )
        self.assertEqual(Booking.objects.count(), 1)


@override_settings(GEMINI_API_KEY='')
class BookingDetailEndpointTests(ApiTestCase):
    def test_get_booking_returns_200_with_diagnosis_context(self):
        conversation = self.make_conversation('My brakes squeal.')
        diagnosis = self.make_diagnosis(conversation)
        booking = Booking.objects.create(
            booking_ref='BK-ABCD1234',
            diagnosis=diagnosis,
            customer_name='Asha Verma',
            phone='+91 98765 43210',
            preferred_date=timezone.localdate() + timedelta(days=2),
        )

        response = self.client.get(f'/api/booking/{booking.id}/')

        self.assertEqual(response.status_code, 200)
        data = response.data['booking']
        self.assertEqual(data['booking_ref'], 'BK-ABCD1234')
        self.assertEqual(data['diagnosis_id'], diagnosis.id)
        self.assertEqual(data['conversation_id'], conversation.id)
        self.assertEqual(data['likely_issue'], diagnosis.likely_issue)

    def test_missing_booking_returns_404(self):
        response = self.client.get('/api/booking/999999/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'Booking 999999 not found.')
