"""Media validator ke unit tests — upload security yahin decide hoti hai.

Sabse important cheez: server CLIENT ke bataye MIME type pe bharosa nahi
karta — file ke pehle bytes (magic bytes) se asli type detect karta hai.
Isliye ek text file ko photo.png naam se bhej bhi do to reject ho jayegi.
"""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from ..services.media_validator import MediaValidationError, validate_and_classify

# Asli file signatures ke chhote samples (magic bytes + thoda padding).
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 32
GIF = b'GIF89a' + b'\x00' * 32
WEBP = b'RIFF' + b'\x20\x00\x00\x00' + b'WEBP' + b'\x00' * 32
WAV = b'RIFF' + b'\x20\x00\x00\x00' + b'WAVE' + b'\x00' * 32
MP3_WITH_ID3 = b'ID3\x03\x00' + b'\x00' * 32
MP3_FRAME = b'\xff\xfb\x90\x00' + b'\x00' * 32
OGG = b'OggS' + b'\x00' * 32
MP4 = b'\x00\x00\x00\x20ftypisom' + b'\x00' * 32
MOV = b'\x00\x00\x00\x20ftypqt  ' + b'\x00' * 32
M4A = b'\x00\x00\x00\x20ftypM4A ' + b'\x00' * 32
WEBM = b'\x1aE\xdf\xa3' + b'\x00' * 10 + b'webm' + b'\x00' * 32
MKV = b'\x1aE\xdf\xa3' + b'\x00' * 40


def _file(name, content, content_type):
    return SimpleUploadedFile(name, content, content_type=content_type)


class _FakeUpload:
    """Chhota duck-typed stand-in — Django ke UploadedFile jaisa hi object.

    Zaroorat kyun? Django 6.x ka `UploadedFile.name` property setter khud hi
    255+ characters ke naam ko truncate kar deta hai (asli multipart request
    path bhi wahi class use karta hai). Isliye validator ka apna 'naam bahut
    lamba hai' guard Django ke through kabhi trigger nahi hota — usse test
    karne ke liye ye simple object bhejte hain, jo validator ko chahiye
    (name/read/seek/size/content_type) bas utna hi deta hai.
    """

    def __init__(self, name, content, content_type):
        self.name = name
        self._io = io.BytesIO(content)
        self.size = len(content)
        self.content_type = content_type

    def read(self, size=-1):
        return self._io.read(size)

    def seek(self, position):
        return self._io.seek(position)


class MediaValidatorTests(TestCase):
    """validate_and_classify() — (media_type, mime_type) ya MediaValidationError."""

    # ---- Images ----

    def test_png_detected_by_magic_bytes(self):
        media_type, mime_type = validate_and_classify(
            _file('photo.png', PNG, 'image/png')
        )
        self.assertEqual((media_type, mime_type), ('image', 'image/png'))

    def test_jpeg_detected(self):
        media_type, mime_type = validate_and_classify(
            _file('photo.jpg', JPEG, 'image/jpeg')
        )
        self.assertEqual((media_type, mime_type), ('image', 'image/jpeg'))

    def test_webp_detected(self):
        media_type, mime_type = validate_and_classify(
            _file('photo.webp', WEBP, 'image/webp')
        )
        self.assertEqual((media_type, mime_type), ('image', 'image/webp'))

    def test_client_mime_ignored_when_magic_bytes_speak(self):
        # Content asli PNG hai lekin client ne galat type bheja — server
        # magic bytes pe bharosa karta hai, isliye phir bhi pass.
        media_type, mime_type = validate_and_classify(
            _file('blob.bin', PNG, 'application/octet-stream')
        )
        self.assertEqual((media_type, mime_type), ('image', 'image/png'))

    def test_spoofed_image_rejected(self):
        # Naam .png aur client type image/png — lekin content text hai.
        with self.assertRaises(MediaValidationError):
            validate_and_classify(
                _file('fake.png', b'This is definitely not an image.', 'image/png')
            )

    def test_gif_detected_but_not_allowed(self):
        with self.assertRaisesMessage(
            MediaValidationError, 'Unsupported file type: image/gif.'
        ):
            validate_and_classify(_file('anim.gif', GIF, 'image/gif'))

    # ---- Audio / video ----

    def test_audio_formats(self):
        cases = [
            ('sound.wav', WAV, 'audio/wav', 'audio/wav'),
            ('song.mp3', MP3_WITH_ID3, 'audio/mpeg', 'audio/mpeg'),
            ('frame.mp3', MP3_FRAME, 'audio/mpeg', 'audio/mpeg'),
            ('voice.ogg', OGG, 'audio/ogg', 'audio/ogg'),
            ('track.m4a', M4A, 'audio/mp4', 'audio/mp4'),
        ]
        for name, content, content_type, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(
                    validate_and_classify(_file(name, content, content_type)),
                    ('audio', expected),
                )

    def test_video_formats(self):
        cases = [
            ('clip.mp4', MP4, 'video/mp4', 'video/mp4'),
            ('clip.mov', MOV, 'video/quicktime', 'video/quicktime'),
            ('clip.webm', WEBM, 'video/webm', 'video/webm'),
        ]
        for name, content, content_type, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(
                    validate_and_classify(_file(name, content, content_type)),
                    ('video', expected),
                )

    def test_matroska_rejected(self):
        with self.assertRaisesMessage(
            MediaValidationError, 'Unsupported file type: video/x-matroska.'
        ):
            validate_and_classify(_file('movie.mkv', MKV, 'video/x-matroska'))

    # ---- Limits ----

    def test_empty_file_rejected(self):
        with self.assertRaisesMessage(
            MediaValidationError, 'The submitted file is empty.'
        ):
            validate_and_classify(_file('empty.png', b'', 'image/png'))

    def test_long_filename_rejected(self):
        # Django khud 255+ naam truncate karta hai (dekho _FakeUpload),
        # isliye validator ke apne guard ko stand-in se test karte hain.
        with self.assertRaisesMessage(
            MediaValidationError, 'File name is too long (max 255 characters).'
        ):
            validate_and_classify(_FakeUpload('a' * 252 + '.png', PNG, 'image/png'))

    def test_oversized_image_rejected(self):
        oversized = PNG + b'\x00' * (10 * 1024 * 1024)
        with self.assertRaisesMessage(
            MediaValidationError, 'Image file is too large (max 10 MB).'
        ):
            validate_and_classify(_file('huge.png', oversized, 'image/png'))
