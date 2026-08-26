import json
import os
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

User = get_user_model()


def make_image(filename='test.png', image_format='PNG', size=(8, 8), content_type='image/png'):
    content = BytesIO()
    Image.new('RGB', size, 'red').save(content, format=image_format)
    return SimpleUploadedFile(filename, content.getvalue(), content_type=content_type)


class MartorImageUploadTestCase(TestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_root.cleanup)
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_root.name,
            MEDIA_URL='/media/',
            MARTOR_UPLOAD_MEDIA_DIR='martor',
            MARTOR_UPLOAD_SAFE_EXTS={'.jpg', '.jpeg', '.png', '.gif', '.webp'},
            MARTOR_UPLOAD_MAX_SIZE=5 * 1024 * 1024,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.url = reverse('martor_image_uploader')
        self.staff = User.objects.create_user(username='martor-staff', password='password', is_staff=True)
        self.user = User.objects.create_user(username='martor-user', password='password')

    def upload(self, image):
        return self.client.post(
            self.url,
            {'markdown-image-upload': image},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            secure=True,
        )

    def test_login_is_required(self):
        response = self.upload(make_image())

        self.assertEqual(response.status_code, 302)

    def test_non_staff_user_is_forbidden(self):
        self.client.force_login(self.user)

        response = self.upload(make_image())

        self.assertEqual(response.status_code, 403)

    def test_valid_image_is_saved_with_detected_format_and_media_url(self):
        self.client.force_login(self.staff)

        response = self.upload(make_image(filename='renamed.jpeg', image_format='PNG', content_type='image/png'))

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertRegex(payload['link'], r'^/media/martor/[0-9a-f-]+\.png$')
        saved_path = os.path.join(self.media_root.name, payload['link'].removeprefix('/media/'))
        self.assertTrue(os.path.isfile(saved_path))
        with Image.open(saved_path) as saved_image:
            self.assertEqual(saved_image.format, 'PNG')

    def test_all_allowed_image_formats_are_accepted(self):
        self.client.force_login(self.staff)

        formats = (
            ('JPEG', 'jpg', 'image/jpeg'),
            ('GIF', 'gif', 'image/gif'),
            ('WEBP', 'webp', 'image/webp'),
        )
        for image_format, extension, content_type in formats:
            with self.subTest(image_format=image_format):
                response = self.upload(make_image(
                    filename='test.%s' % extension,
                    image_format=image_format,
                    content_type=content_type,
                ))

                self.assertEqual(response.status_code, 200)
                payload = json.loads(response.content)
                self.assertTrue(payload['link'].endswith('.%s' % extension))

    def test_unsupported_extension_is_rejected(self):
        self.client.force_login(self.staff)

        response = self.upload(make_image(filename='test.svg'))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(os.path.exists(os.path.join(self.media_root.name, 'martor')))

    def test_unsupported_content_type_is_rejected(self):
        self.client.force_login(self.staff)

        response = self.upload(make_image(content_type='application/octet-stream'))

        self.assertEqual(response.status_code, 400)

    def test_invalid_image_is_rejected(self):
        self.client.force_login(self.staff)
        image = SimpleUploadedFile('fake.png', b'not an image', content_type='image/png')

        response = self.upload(image)

        self.assertEqual(response.status_code, 400)

    @override_settings(MARTOR_UPLOAD_MAX_SIZE=3)
    def test_oversized_image_is_rejected(self):
        self.client.force_login(self.staff)

        response = self.upload(make_image())

        self.assertEqual(response.status_code, 400)

    def test_non_ajax_request_is_rejected(self):
        self.client.force_login(self.staff)

        response = self.client.post(self.url, {'markdown-image-upload': make_image()}, secure=True)

        self.assertEqual(response.status_code, 400)
