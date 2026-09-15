import logging
import math
import re
import uuid
import warnings
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps, UnidentifiedImageError


logger = logging.getLogger(__name__)
AVATAR_MAX_BYTES = 5 * 1024 * 1024
AVATAR_MAX_PIXELS = 25_000_000
AVATAR_SIZE = 512


def prepare_avatar(upload, x, y, size):
    """Validate the original image and crop in EXIF-oriented pixel coordinates."""
    if upload.size > AVATAR_MAX_BYTES:
        raise ValidationError('사진은 5MB 이하로 올려주세요.')
    raw = upload.read(AVATAR_MAX_BYTES + 1)
    if len(raw) > AVATAR_MAX_BYTES:
        raise ValidationError('사진은 5MB 이하로 올려주세요.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as probe:
                if probe.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValidationError('JPG, PNG, WebP 사진만 사용할 수 있습니다.')
                if getattr(probe, 'n_frames', 1) != 1:
                    raise ValidationError('움직이는 이미지는 사용할 수 없습니다.')
                width, height = probe.size
                if width * height > AVATAR_MAX_PIXELS or max(width, height) > 10000:
                    raise ValidationError('사진은 2,500만 화소 이하, 가로·세로 각각 10,000px 이하로 올려주세요.')
                probe.verify()
            with Image.open(BytesIO(raw)) as original:
                oriented = ImageOps.exif_transpose(original)
                width, height = oriented.size
                if (not all(math.isfinite(value) for value in (x, y, size)) or size < 1
                        or x < 0 or y < 0 or x + size > width + 0.001 or y + size > height + 0.001):
                    raise ValidationError('사진의 잘라낼 영역을 다시 지정해주세요.')
                rgba = oriented.convert('RGBA')
                # Clamp only subpixel rounding at the image edge, never arbitrary out-of-bounds crops.
                cropped = rgba.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS,
                                      box=(x, y, min(x + size, width), min(y + size, height)))
                cropped.info.clear()
                output = BytesIO()
                cropped.save(output, 'WEBP', quality=85, method=4)
                return ContentFile(output.getvalue())
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValidationError('사진을 읽을 수 없습니다. 정상적인 JPG, PNG, WebP 파일을 선택해주세요.') from exc


def new_avatar_name():
    return 'avatars/%s.webp' % uuid.uuid4().hex


def delete_unused_avatar(name):
    """Delete only managed, unreferenced files after the database commit succeeds."""
    from judge.models import Profile

    if not name or not re.fullmatch(r'avatars/[0-9a-f]{32}\.webp', name):
        return
    try:
        if not Profile.objects.filter(avatar=name).exists():
            default_storage.delete(name)
    except Exception:
        # A storage outage must not turn a committed profile update into an apparent failure.
        logger.exception('Could not clean up an unused profile image')
