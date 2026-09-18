import json
import os
import uuid
import warnings
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseRedirect
from django.views.decorators.http import require_POST
from PIL import Image, UnidentifiedImageError

from judge.models import Submission

__all__ = ['rejudge_submission']


@login_required
@require_POST
def rejudge_submission(request):
    if 'id' not in request.POST or not request.POST['id'].isdigit():
        return HttpResponseBadRequest()

    try:
        submission = Submission.objects.get(id=request.POST['id'])
    except Submission.DoesNotExist:
        return HttpResponseBadRequest()

    if not submission.problem.is_subs_manageable_by(request.user):
        return HttpResponseForbidden()

    submission.judge(rejudge=True, rejudge_user=request.user)

    redirect = request.POST.get('path', None)

    return HttpResponseRedirect(redirect) if redirect else HttpResponse('success', content_type='text/plain')


def django_uploader(image):
    ext = os.path.splitext(image.name)[1].lower()
    if ext not in settings.MARTOR_UPLOAD_SAFE_EXTS:
        raise ValueError('Unsupported image extension')
    if image.size > settings.MARTOR_UPLOAD_MAX_SIZE:
        raise ValueError('Image is too large')
    if image.content_type not in {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}:
        raise ValueError('Unsupported image content type')

    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            uploaded_image = Image.open(image)
            uploaded_image.verify()
            image_format = uploaded_image.format
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError):
        raise ValueError('Invalid image')
    finally:
        image.seek(0)

    extensions = {
        'JPEG': '.jpg',
        'PNG': '.png',
        'GIF': '.gif',
        'WEBP': '.webp',
    }
    try:
        detected_ext = extensions[image_format]
    except KeyError:
        raise ValueError('Unsupported image format')

    name = str(uuid.uuid4()) + detected_ext
    saved_name = default_storage.save(os.path.join(settings.MARTOR_UPLOAD_MEDIA_DIR, name), image)
    url_base = getattr(settings, 'MARTOR_UPLOAD_URL_PREFIX',
                       urljoin(settings.MEDIA_URL, settings.MARTOR_UPLOAD_MEDIA_DIR))
    if not url_base.endswith('/'):
        url_base += '/'
    return json.dumps({'status': 200, 'name': '', 'link': urljoin(url_base, os.path.basename(saved_name))})


@login_required
def martor_image_uploader(request):
    if request.method != 'POST' or not request.is_ajax() or 'markdown-image-upload' not in request.FILES:
        return HttpResponseBadRequest('Invalid request')

    if not request.user.is_staff:
        return HttpResponseForbidden('Staff access required')

    try:
        image = request.FILES['markdown-image-upload']
        data = django_uploader(image)
    except ValueError as error:
        return HttpResponseBadRequest(str(error))
    return HttpResponse(data, content_type='application/json')
