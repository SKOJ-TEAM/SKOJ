import os
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError

from judge.models.problem import ProblemGroup


def guide_image_upload_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return 'guide-images/%s%s' % (uuid.uuid4(), extension)


def validate_guide_image(upload):
    extension = os.path.splitext(upload.name)[1].lower()
    safe_extensions = getattr(settings, 'MARTOR_UPLOAD_SAFE_EXTS', {'.jpg', '.jpeg', '.png', '.gif', '.webp'})
    if extension not in safe_extensions:
        raise ValidationError('JPG, PNG, GIF, WEBP 이미지만 업로드할 수 있습니다.')
    if upload.size > getattr(settings, 'MARTOR_UPLOAD_MAX_SIZE', 5 * 1024 * 1024):
        raise ValidationError('이미지는 5MB 이하여야 합니다.')
    try:
        image = Image.open(upload)
        image.verify()
        if image.format not in {'JPEG', 'PNG', 'GIF', 'WEBP'}:
            raise ValidationError('지원하지 않는 이미지 형식입니다.')
        expected_extensions = {
            'JPEG': {'.jpg', '.jpeg'}, 'PNG': {'.png'}, 'GIF': {'.gif'}, 'WEBP': {'.webp'},
        }
        if extension not in expected_extensions[image.format]:
            raise ValidationError('파일 확장자와 실제 이미지 형식이 일치하지 않습니다.')
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError):
        raise ValidationError('올바른 이미지 파일이 아닙니다.')
    finally:
        upload.seek(0)


class GuideImage(models.Model):
    title = models.CharField(max_length=150, verbose_name='자료명')
    alt_text = models.CharField(max_length=200, blank=True, verbose_name='대체 텍스트')
    image = models.ImageField(upload_to=guide_image_upload_path, validators=[validate_guide_image], verbose_name='이미지')
    uploaded_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='guide_images', verbose_name='업로더',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='등록일')

    def __str__(self):
        return self.title

    @property
    def markdown_alt(self):
        return self.alt_text or self.title

    class Meta:
        ordering = ('-created_at', '-id')
        verbose_name = '사진 자료'
        verbose_name_plural = '사진 자료'


@receiver(post_delete, sender=GuideImage)
def delete_guide_image_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)


class AlgorithmGuide(models.Model):
    problem_group = models.ForeignKey(
        ProblemGroup,
        related_name='algorithm_guides',
        on_delete=models.PROTECT,
        verbose_name=_('문제 그룹'),
    )
    title = models.CharField(max_length=150, verbose_name=_('title'))
    summary = models.CharField(max_length=300, verbose_name=_('summary'))
    content = models.TextField(verbose_name=_('content'))
    is_published = models.BooleanField(default=False, db_index=True, verbose_name=_('published'))
    order = models.PositiveIntegerField(default=0, db_index=True, verbose_name=_('order'))
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='algorithm_guides',
        verbose_name=_('created by'),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('created at'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('updated at'))

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('guide_detail', args=(self.problem_group.name, self.pk))

    class Meta:
        ordering = ('order', 'title', 'id')
        verbose_name = '가이드'
        verbose_name_plural = '가이드'
