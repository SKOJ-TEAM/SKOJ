from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


User = get_user_model()


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class UserListViewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_superuser(
            username='user-list-viewer',
            email='viewer@example.com',
            password='test-password',
            first_name='목록 관리자',
        )
        cls.normal = User.objects.create_user(username='normal-login', first_name='홍길동')
        cls.staff = User.objects.create_user(username='staff-login', first_name='김교수', is_staff=True)
        cls.unnamed = User.objects.create_user(username='unnamed-login', first_name='')

    def setUp(self):
        self.client.force_login(self.viewer)

    def test_list_displays_names_for_all_user_types(self):
        response = self.client.get(reverse('user_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<th class="header first_name">이름</th>', html=True)
        self.assertContains(response, '<a href="/user/normal-login">홍길동</a>', html=True)
        self.assertContains(response, '<a href="/user/staff-login">김교수</a>', html=True)
        self.assertNotContains(response, '>normal-login</a>')
        self.assertNotContains(response, '>staff-login</a>')
        self.assertNotContains(response, 'class="user-name"')

    def test_list_leaves_missing_name_blank_without_username_fallback(self):
        response = self.client.get(reverse('user_list'))

        self.assertContains(response, '<a href="/user/unnamed-login"></a>', html=True)
        self.assertNotContains(response, '>unnamed-login</a>')

    def test_list_escapes_name_text(self):
        self.normal.first_name = '<script>alert(1)</script>'
        self.normal.save(update_fields=('first_name',))

        response = self.client.get(reverse('user_list'))

        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_search_uses_name_and_updates_placeholder(self):
        response = self.client.get(reverse('user_list'), {'search': '홍길'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'placeholder="이름 검색"')
        self.assertContains(response, 'id="user-normal-login"')
        self.assertNotContains(response, 'id="user-staff-login"')

    def test_search_does_not_match_username(self):
        response = self.client.get(reverse('user_list'), {'search': 'normal-login'})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="user-normal-login"')
