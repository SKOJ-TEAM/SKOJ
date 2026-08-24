from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


User = get_user_model()


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class ContestListAuthenticationTestCase(TestCase):
    def test_current_contest_list_redirects_anonymous_user_to_login(self):
        response = self.client.get('/contests/0/')

        self.assertRedirects(response, '/accounts/login/?next=/contests/0/', fetch_redirect_response=False)

    def test_past_contest_list_redirects_anonymous_user_to_login(self):
        response = self.client.get('/contests/0/past')

        self.assertRedirects(response, '/accounts/login/?next=/contests/0/past', fetch_redirect_response=False)


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class ContestListPageTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='contest-list-user', password='test-password')
        self.client.force_login(self.user)
        self.contest_response = self.client.get('/contests/0/')
        self.practice_response = self.client.get('/contests/1/')

    def test_contest_list_renders(self):
        self.assertEqual(self.contest_response.status_code, 200)
        self.assertEqual(self.practice_response.status_code, 404)

    def test_page_intro_copy(self):
        contest_content = self.contest_response.content.decode()
        self.assertIn('<h1 class="contest-page-title">대회</h1>', contest_content)
        self.assertIn('진행 중이거나 예정된 대회를 확인하세요.', contest_content)

    def test_list_tab_label(self):
        self.assertIn('대회 목록', self.contest_response.content.decode())

    def test_no_stray_litmus_primary_variable(self):
        content = self.contest_response.content.decode()
        self.assertNotIn('LITMUS-Primary', content)
        self.assertNotIn('LITMUS-primary', content)


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class ContestPastListPageTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='contest-past-list-user', password='test-password')
        self.client.force_login(self.user)
        self.contest_response = self.client.get('/contests/0/past')
        self.practice_response = self.client.get('/contests/1/past')

    def test_past_list_renders(self):
        self.assertEqual(self.contest_response.status_code, 200)
        self.assertEqual(self.practice_response.status_code, 404)

    def test_page_intro_copy(self):
        contest_content = self.contest_response.content.decode()
        self.assertIn('<h1 class="contest-page-title">대회</h1>', contest_content)
        self.assertIn('종료된 대회를 확인하세요.', contest_content)
