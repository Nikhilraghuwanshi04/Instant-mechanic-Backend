"""Uploaded files ki security validation.

Client ke bheje MIME type pe bharosa NAHI karte — file ke pehle bytes
(magic bytes) se asli type detect karte hain. Ye spoofing se bachata hai.
"""

from django.conf import settings


class MediaValidationError(Exception):
    """Jab uploaded file koi rule todhe (type, size, naam)."""


ALLOWED_MIME_TYPES = {
    'image': {'image/jpeg', 'image/png', 'image/webp'},
    'audio': {'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/mp4', 'audio/webm'},
    'video': {'video/mp4', 'video/quicktime', 'video/webm'},
}

MAX_SIZE_MB = {
    'image': settings.MAX_IMAGE_MB,
    'audio': settings.MAX_AUDIO_MB,
    'video': settings.MAX_VIDEO_MB,
}


def _detect_mime(head, client_mime):
    """File ke pehle 64 bytes (head) se asli MIME type detect karta hai.

    Detection broad hai (GIF/MKV bhi pakadta hai) taaki allowlist check
    ka matlab rahe — detect hone ke baad allowed list se match karaya jata hai.
    """
    if head.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if head.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if len(head) >= 12 and head[0:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image/webp'
    if len(head) >= 12 and head[0:4] == b'RIFF' and head[8:12] == b'WAVE':
        return 'audio/wav'
    if head.startswith(b'ID3'):
        return 'audio/mpeg'
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return 'audio/mpeg'
    if head.startswith(b'OggS'):
        return 'audio/ogg'
    if len(head) >= 12 and head[4:8] == b'ftyp':
        brand = head[8:12]
        if brand == b'M4A ':
            return 'audio/mp4'
        if brand == b'qt  ':
            return 'video/quicktime'
        if client_mime.startswith('audio/'):
            return 'audio/mp4'
        return 'video/mp4'
    if head.startswith(b'\x1aE\xdf\xa3'):
        if b'webm' in head:
            if client_mime.startswith('audio/'):
                return 'audio/webm'
            return 'video/webm'
        return 'video/x-matroska'
    return None


def validate_and_classify(uploaded_file):
    """File ko validate karke (media_type, mime_type) return karta hai.

    Kuch bhi galat mile toh MediaValidationError raise hota hai —
    view usse pakad kar 400 response banata hai.
    """
    if len(uploaded_file.name) > 255:
        raise MediaValidationError('File name is too long (max 255 characters).')

    head = uploaded_file.read(64)
    uploaded_file.seek(0)

    if not head:
        raise MediaValidationError('The submitted file is empty.')

    mime_type = _detect_mime(head, uploaded_file.content_type or '')
    if mime_type is None:
        raise MediaValidationError(
            'Unsupported file type. Allowed formats: JPEG/PNG/WEBP images, '
            'MP3/WAV/OGG audio, MP4/MOV/WEBM video.'
        )

    media_type = mime_type.split('/')[0]
    if mime_type not in ALLOWED_MIME_TYPES[media_type]:
        raise MediaValidationError(f'Unsupported file type: {mime_type}.')

    limit_mb = MAX_SIZE_MB[media_type]
    if uploaded_file.size > limit_mb * 1024 * 1024:
        raise MediaValidationError(
            f'{media_type.title()} file is too large (max {limit_mb} MB).'
        )

    return media_type, mime_type
