from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.middleware.csrf import get_token
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from judge.jinja2.gravatar import gravatar
from judge.models import Language, Profile
from judge.utils.avatars import AVATAR_MAX_BYTES, delete_unused_avatar, prepare_avatar
from judge.views.user import UserList


def photo(fmt='PNG', size=(120, 80), **options):
    output = BytesIO()
    Image.new('RGB', size, 'red').save(output, fmt, **options)
    return SimpleUploadedFile('photo.' + fmt.lower(), output.getvalue(), content_type='image/' + fmt.lower())


class AvatarImageTest(SimpleTestCase):
    def test_supported_formats_are_reencoded_to_square_webp(self):
        for fmt in ('JPEG', 'PNG', 'WEBP'):
            with self.subTest(fmt=fmt):
                output = prepare_avatar(photo(fmt), 20, 0, 80)
                with Image.open(output) as result:
                    self.assertEqual(result.size, (512, 512))
                    self.assertEqual(result.format, 'WEBP')
                    self.assertNotIn('exif', result.info)

    def test_exact_five_megabytes_allowed_but_one_byte_more_rejected(self):
        raw = photo('JPEG').read()
        boundary = raw + b'\0' * (AVATAR_MAX_BYTES - len(raw))
        self.assertTrue(prepare_avatar(SimpleUploadedFile('ok.jpg', boundary), 0, 0, 80))
        with self.assertRaisesMessage(ValidationError, '5MB'):
            prepare_avatar(SimpleUploadedFile('large.jpg', boundary + b'0'), 0, 0, 80)

    def test_bounded_read_does_not_trust_reported_size(self):
        upload = SimpleUploadedFile('large.jpg', b'0' * (AVATAR_MAX_BYTES + 1))
        upload.size = 1
        with self.assertRaisesMessage(ValidationError, '5MB'):
            prepare_avatar(upload, 0, 0, 80)

    def test_fake_corrupt_and_gif_files_are_rejected(self):
        for upload in (SimpleUploadedFile('fake.jpg', b'<svg></svg>', content_type='image/jpeg'),
                       SimpleUploadedFile('broken.png', photo().read()[:40]), photo('GIF')):
            with self.subTest(name=upload.name), self.assertRaises(ValidationError):
                prepare_avatar(upload, 0, 0, 80)

    def test_animated_webp_is_rejected(self):
        output = BytesIO()
        Image.new('RGB', (80, 80), 'red').save(
            output, 'WEBP', save_all=True, append_images=[Image.new('RGB', (80, 80), 'blue')], duration=100)
        with self.assertRaisesMessage(ValidationError, '움직이는'):
            prepare_avatar(SimpleUploadedFile('animated.webp', output.getvalue()), 0, 0, 80)

    def test_pixel_and_dimension_limits(self):
        with patch('judge.utils.avatars.AVATAR_MAX_PIXELS', 100), self.assertRaises(ValidationError):
            prepare_avatar(photo(), 0, 0, 80)
        with self.assertRaises(ValidationError):
            prepare_avatar(photo(size=(10001, 1)), 0, 0, 1)

    def test_invalid_crop_coordinates(self):
        for coords in ((-1, 0, 80), (0, -1, 80), (0, 0, 0), (0, 0, 81), (41, 0, 80),
                       (float('nan'), 0, 80), (0, 0, float('inf'))):
            with self.subTest(coords=coords), self.assertRaises(ValidationError):
                prepare_avatar(photo(), *coords)

    def test_selected_region_is_used(self):
        original = Image.new('RGB', (120, 80), 'red')
        original.paste('blue', (80, 0, 120, 80))
        raw = BytesIO()
        original.save(raw, 'PNG')
        result = Image.open(prepare_avatar(SimpleUploadedFile('crop.png', raw.getvalue()), 80, 20, 40))
        red, green, blue = result.convert('RGB').getpixel((256, 256))
        self.assertLess(red, 10)
        self.assertGreater(blue, 240)

    def test_exif_orientation_applied_and_metadata_removed(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = 'private description'
        output = prepare_avatar(photo('JPEG', size=(120, 80), exif=exif), 0, 40, 80)
        encoded = output.read()
        with Image.open(BytesIO(encoded)) as result:
            self.assertEqual(result.size, (512, 512))
            self.assertFalse(result.getexif())
            self.assertNotIn(b'private description', encoded)


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False,
                   CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class AvatarViewTest(TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='skoj-avatar-test-')
        self.addCleanup(directory.cleanup)
        settings = override_settings(MEDIA_ROOT=directory.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.user = get_user_model().objects.create_user(username='avatar-user', first_name='사진 사용자')
        self.other = get_user_model().objects.create_user(username='avatar-other', first_name='다른 사용자')
        self.client.force_login(self.user)
        self.url = reverse('user_edit_avatar')

    def upload(self, **extra):
        data = dict(action='upload', image=photo(), crop_x=20, crop_y=0, crop_size=80)
        data.update(extra)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, data)
        return response

    def avatar_name(self, user=None):
        return Profile.objects.get(user=user or self.user).avatar.name

    def test_upload_updates_only_current_user(self):
        response = self.upload(user=self.other.pk, profile=self.other.profile.pk)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['has_avatar'])
        self.assertTrue(default_storage.exists(self.avatar_name()))
        self.assertFalse(self.avatar_name(self.other))
        self.assertEqual(response.json()['avatar_url'], default_storage.url(self.avatar_name()))
        self.assertEqual(default_storage.listdir('avatars')[1], [self.avatar_name().split('/')[1]])

    def test_auth_method_and_csrf_are_required(self):
        self.assertEqual(Client().post(self.url, {'action': 'remove'}).status_code, 302)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.url, {'action': 'remove'}).status_code, 403)
        page = csrf_client.get(reverse('user_edit_profile'))
        self.assertEqual(page.status_code, 200)
        token = get_token(page.wsgi_request)
        self.assertEqual(csrf_client.post(self.url, {'action': 'remove', 'csrfmiddlewaretoken': token}).status_code, 200)

    def test_muted_profile_cannot_change_photo(self):
        Profile.objects.filter(user=self.user).update(mute=True)
        self.assertEqual(self.upload().status_code, 404)
        self.assertFalse(self.avatar_name())

    def test_invalid_request_preserves_old_file(self):
        self.upload()
        old_name = self.avatar_name()
        cases = ({'crop_x': -1}, {'crop_size': ''}, {'image': [photo(), photo()]},
                 {'action': 'invalid'}, {'action': 'remove'},
                 {'image': SimpleUploadedFile('fake.jpg', b'<svg/>')}, {'crop_x': 'nan'})
        for extra in cases:
            with self.subTest(extra=extra.keys()):
                self.assertEqual(self.upload(**extra).status_code, 400)
                self.assertEqual(self.avatar_name(), old_name)
                self.assertTrue(default_storage.exists(old_name))

    def test_replacement_deletes_previous_file_only_after_commit(self):
        self.upload()
        old_name = self.avatar_name()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, dict(action='upload', image=photo(), crop_x=0, crop_y=0, crop_size=80))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(default_storage.exists(old_name))
        self.assertNotEqual(self.avatar_name(), old_name)
        self.assertFalse(default_storage.exists(old_name))

    def test_remove_returns_gravatar_and_cleans_up_file(self):
        self.upload()
        old_name = self.avatar_name()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, {'action': 'remove'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['has_avatar'])
        self.assertIn('gravatar.com/avatar/', response.json()['avatar_url'])
        self.assertFalse(self.avatar_name())
        self.assertFalse(default_storage.exists(old_name))
        self.assertEqual(self.client.post(self.url, {'action': 'remove'}).status_code, 200)

    def test_database_failure_cleans_new_file_and_preserves_old(self):
        self.upload()
        old_name = self.avatar_name()
        with patch.object(Profile, 'save', side_effect=RuntimeError('simulated DB failure')):
            with self.assertRaises(RuntimeError):
                self.upload()
        self.assertEqual(self.avatar_name(), old_name)
        self.assertEqual(default_storage.listdir('avatars')[1], [old_name.split('/')[1]])

    def test_storage_failure_preserves_old_photo(self):
        self.upload()
        old_name = self.avatar_name()
        with patch('judge.views.avatar.default_storage.save', side_effect=OSError('simulated storage failure')):
            with self.assertRaises(OSError):
                self.upload()
        self.assertEqual(self.avatar_name(), old_name)
        self.assertTrue(default_storage.exists(old_name))

    def test_account_deletion_cleans_up_avatar(self):
        self.upload()
        old_name = self.avatar_name()
        with self.captureOnCommitCallbacks(execute=True):
            self.user.delete()
        self.assertFalse(default_storage.exists(old_name))

    def test_cleanup_preserves_referenced_and_unmanaged_files(self):
        self.upload()
        old_name = self.avatar_name()
        with patch('judge.utils.avatars.default_storage.delete') as delete:
            for name in (old_name, 'unmanaged.jpg', 'avatars/../important.webp'):
                delete_unused_avatar(name)
            delete.assert_not_called()

    def test_cleanup_outage_does_not_fail_committed_update(self):
        self.upload()
        with patch('judge.utils.avatars.default_storage.delete', side_effect=OSError('storage offline')):
            with self.assertLogs('judge.utils.avatars', level='ERROR'):
                response = self.upload()
        self.assertEqual(response.status_code, 200)

    def test_helper_prefers_avatar_and_keeps_gravatar_fallbacks(self):
        self.upload()
        profile = Profile.objects.select_related('user').get(user=self.user)
        with self.assertNumQueries(0):
            self.assertEqual(gravatar(profile), profile.avatar.url)
            self.assertEqual(gravatar(profile.user), profile.avatar.url)
        self.assertIn('gravatar.com/avatar/', gravatar(self.other.profile))
        self.assertIn('gravatar.com/avatar/', gravatar('example@example.com'))
        self.assertIn('f=y', gravatar(profile, default=True))
        profile.mute = True
        self.assertIn('f=y', gravatar(profile))

    def test_ranking_and_directory_show_uploaded_avatar_beside_name(self):
        self.upload()
        for url in (reverse('gamification_ranking'), reverse('user_list')):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="profile-avatar-name"')
                self.assertContains(response, 'class="profile-avatar" src="%s"' % default_storage.url(self.avatar_name()))
                self.assertContains(response, '사진 사용자')

    def test_directory_queryset_needs_no_extra_avatar_queries(self):
        self.upload()
        request = self.client.get(reverse('user_list')).wsgi_request
        view = UserList()
        view.setup(request)
        profiles = list(view.get_queryset())
        with self.assertNumQueries(0):
            for profile in profiles:
                gravatar(profile, 32)

    def test_edit_page_has_separate_avatar_form_and_existing_fields_remain(self):
        self.upload()
        old_name = self.avatar_name()
        response = self.client.get(reverse('user_edit_profile'))
        self.assertContains(response, 'id="avatar-form"')
        self.assertContains(response, 'id="avatar-zoom"')
        self.assertContains(response, '최대 5MB')
        html = response.content.decode()
        self.assertLess(html.index('</form>', html.index('id="avatar-form"')), html.index('id="edit-form"'))
        language, _ = Language.objects.get_or_create(key='AVTEST', defaults={'name': 'Avatar test', 'short_name': 'AT'})
        response = self.client.post(reverse('user_edit_profile'), {
            'about': 'Updated about', 'timezone': 'Asia/Seoul', 'language': language.pk, 'site_theme': 'light',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Profile.objects.get(user=self.user).about, 'Updated about')
        self.assertEqual(self.avatar_name(), old_name)
