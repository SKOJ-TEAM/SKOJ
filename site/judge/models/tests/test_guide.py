from django.contrib import admin
from django.db.models.deletion import ProtectedError
import json
import os
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from judge.admin.guide import AlgorithmGuideAdmin, AlgorithmGuideForm, GuideImageAdmin
from judge.models import AlgorithmGuide, GuideImage, ProblemGroup
from judge.models.tests.util import CommonDataMixin
from judge.widgets import AdminMartorWidget


class AlgorithmGuideModelTest(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.problem_group = ProblemGroup.objects.create(name='sorting-guide', full_name='정렬')

    def test_string_and_absolute_url(self):
        guide = AlgorithmGuide.objects.create(
            problem_group=self.problem_group,
            title='버블 정렬',
            summary='버블 정렬의 원리를 배웁니다.',
            content='# 버블 정렬',
        )

        self.assertEqual(str(guide), '버블 정렬')
        self.assertEqual(
            guide.get_absolute_url(),
            reverse('guide_detail', args=('sorting-guide', guide.pk)),
        )

    def test_problem_group_with_guides_is_protected(self):
        AlgorithmGuide.objects.create(
            problem_group=self.problem_group,
            title='버블 정렬',
            summary='요약',
            content='본문',
        )

        with self.assertRaises(ProtectedError):
            self.problem_group.delete()


class AlgorithmGuideAdminTest(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.problem_group = ProblemGroup.objects.create(name='graph-guide', full_name='그래프')

    def test_form_uses_markdown_editor(self):
        form = AlgorithmGuideForm()

        self.assertIsInstance(form.fields['content'].widget, AdminMartorWidget)
        self.assertNotIn('markdown-image-upload', form.fields['content'].widget.render('content', '', attrs={}))
        self.assertIn('guide-image-library.js', str(form.media))
        self.assertIn('guide-image-library.css', str(form.media))

    def test_admin_sidebar_lists_images_as_top_level_menu(self):
        menu = settings.WPADMIN['admin']['custom_menu']

        self.assertIn(('judge.AlgorithmGuide', 'fa-book'), menu)
        self.assertIn(('judge.GuideImage', 'fa-picture-o'), menu)

    def test_admin_records_creator(self):
        guide_admin = AlgorithmGuideAdmin(AlgorithmGuide, admin.site)
        request = RequestFactory().post('/admin/judge/algorithmguide/add/')
        request.user = self.users['superuser']
        guide = AlgorithmGuide(
            problem_group=self.problem_group,
            title='그래프 탐색',
            summary='요약',
            content='본문',
        )

        guide_admin.save_model(request, guide, form=None, change=False)

        self.assertEqual(guide.created_by, self.users['superuser'])


class GuideImageAdminTest(CommonDataMixin, TestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_root.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.media_root.name, MEDIA_URL='/media/')
        self.override.enable()
        self.addCleanup(self.override.disable)

    def test_admin_records_uploader_and_library_returns_markdown_data(self):
        image_admin = GuideImageAdmin(GuideImage, admin.site)
        request = RequestFactory().post('/admin/judge/guideimage/add/')
        request.user = self.users['superuser']
        image = GuideImage(
            title='연결 리스트', alt_text='연결 리스트 구조',
            image=SimpleUploadedFile('linked-list.png', self._png(), content_type='image/png'),
        )
        image.full_clean()
        image_admin.save_model(request, image, form=None, change=False)

        library_request = RequestFactory().get('/admin/judge/guideimage/library/')
        library_request.user = self.users['superuser']
        response = image_admin.library(library_request)
        payload = json.loads(response.content)

        self.assertEqual(image.uploaded_by, self.users['superuser'])
        self.assertEqual(payload['images'][0]['alt'], '연결 리스트 구조')
        self.assertIn('/media/guide-images/', payload['images'][0]['url'])

    def test_deleting_record_deletes_image_file(self):
        image = GuideImage.objects.create(
            title='삭제 대상', image=SimpleUploadedFile('delete.png', self._png(), content_type='image/png'),
        )
        path = image.image.path
        self.assertTrue(os.path.exists(path))

        image.delete()

        self.assertFalse(os.path.exists(path))

    @staticmethod
    def _png():
        from io import BytesIO
        from PIL import Image
        content = BytesIO()
        Image.new('RGB', (8, 8), 'red').save(content, format='PNG')
        return content.getvalue()
