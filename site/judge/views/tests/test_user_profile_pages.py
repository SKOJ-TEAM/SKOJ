from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from judge.models import Language, Submission
from judge.models.tests.util import create_problem


User = get_user_model()


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class UserProfilePagesTestCase(TestCase):
    fixtures = ['language_all.json']

    @classmethod
    def setUpTestData(cls):
        cls.target = User.objects.create_user(username='profile-target')
        cls.staff = User.objects.create_user(username='profile-staff', is_staff=True)
        cls.normal = User.objects.create_user(username='profile-normal')
        cls.language = Language.objects.get(key='PY3')

        for index in range(11):
            points = 20 - index
            problem = create_problem(
                code='profile-problem-%02d' % index,
                name='프로필 문제 %02d' % index,
                points=points,
                is_public=True,
            )
            Submission.objects.create(
                user=cls.target.profile,
                problem=problem,
                language=cls.language,
                status='D',
                result='AC',
                points=points,
                case_points=1,
                case_total=1,
            )

    def test_profile_contest_page_is_not_routable(self):
        response = self.client.get('/user/profile-target/contests')

        self.assertEqual(response.status_code, 404)

    def test_profile_navigation_does_not_show_contest_tab(self):
        self.client.force_login(self.target)
        response = self.client.get(reverse('user_page', args=(self.target.username,)))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '/contests')
        self.assertNotContains(response, '과제/대회')

    def test_solved_page_uses_csp_safe_load_more_handler(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse('user_problems', args=(self.target.username,)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="pp-load-more-link" href="#"', html=False)
        self.assertContains(response, "$('#pp-load-more-link').on('click'", html=False)
        self.assertNotContains(response, 'javascript:load_more_pp()', html=False)

    def test_solved_ajax_returns_the_next_page(self):
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse('user_pp_ajax', args=(self.target.username,)),
            {'start': 10, 'end': 20},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('프로필 문제 10', payload['results'])
        self.assertFalse(payload['has_more'])

    def test_solved_page_and_ajax_remain_staff_only(self):
        self.client.force_login(self.normal)

        page_response = self.client.get(reverse('user_problems', args=(self.target.username,)))
        ajax_response = self.client.get(reverse('user_pp_ajax', args=(self.target.username,)))

        self.assertEqual(page_response.status_code, 403)
        self.assertEqual(ajax_response.status_code, 403)
