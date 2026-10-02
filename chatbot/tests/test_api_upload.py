"""POST /api/upload/ ke integration tests — multipart form-data ka safar.

Upload view file ko disk pe likhta hai (FileField → MEDIA_ROOT), isliye is
test class mein MEDIA_ROOT ko ek temp folder pe point karte hain — warna
test uploads tumhari asli backend/media/ directory mein gir jate.

Ye override safe hai: FileSystemStorage MEDIA_ROOT badalne pe apni cached
location khud refresh karta hai (Django ka StorageSettingsMixin), aur
override disable hote hi wapas dev MEDIA_ROOT pe switch ho jata hai.
"""

import os
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from ..models import Conversation, MediaUpload
from .helpers import PNG_BYTES, ApiTestCase, png_file


@override_settings(GEMINI_API_KEY='')
class UploadEndpointTests(ApiTestCase):
    URL = '/api/upload/'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix='acm-test-media-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def test_new_conversation_with_png_returns_201_and_writes_file(self):
        response = self.client.post(self.URL, {'file': png_file()}, format='multipart')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['conversation_title'], 'Upload: photo.png')

        media = MediaUpload.objects.get()
        self.assertEqual(media.media_type, 'image')
        self.assertEqual(media.mime_type, 'image/png')
        self.assertEqual(media.original_name, 'photo.png')
        self.assertEqual(media.size_bytes, len(PNG_BYTES))
        self.assertTrue(os.path.isfile(media.file.path))
        # File temp dir ke andar hi likhi gayi — dev media/ mein kuch nahi gira.
        self.assertTrue(media.file.path.startswith(self._media_root))
        self.assertIn('/media/uploads/', response.data['media']['file'])

    def test_existing_conversation_returns_200(self):
        conversation = self.make_conversation()
        response = self.client.post(
            self.URL,
            {'file': png_file(), 'conversation_id': conversation.id},
            format='multipart',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['conversation_id'], conversation.id)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(conversation.media_uploads.count(), 1)

    def test_spoofed_file_returns_400_and_saves_nothing(self):
        fake = SimpleUploadedFile('fake.png', b'This is not an image.', 'image/png')
        response = self.client.post(self.URL, {'file': fake}, format='multipart')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Unsupported file type', response.data['file'][0])
        self.assertEqual(MediaUpload.objects.count(), 0)

    def test_empty_file_returns_400(self):
        empty = SimpleUploadedFile('empty.png', b'', content_type='image/png')
        response = self.client.post(self.URL, {'file': empty}, format='multipart')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['file'][0], 'The submitted file is empty.')

    def test_missing_file_returns_400(self):
        response = self.client.post(self.URL, {}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['file'][0], 'No file was submitted.')

    def test_missing_conversation_returns_404(self):
        response = self.client.post(
            self.URL,
            {'file': png_file(), 'conversation_id': 999999},
            format='multipart',
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'Conversation 999999 not found.')
        self.assertEqual(MediaUpload.objects.count(), 0)
