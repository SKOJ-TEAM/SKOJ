from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from judge.models.tests.util import create_problem, create_problem_group


User = get_user_model()


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class ProblemListAuthenticationTestCase(TestCase):
    def test_problem_list_redirects_anonymous_user_to_login(self):
        response = self.client.get('/problems/')

        self.assertRedirects(response, '/accounts/login/?next=/problems/', fetch_redirect_response=False)

    def test_problem_list_renders_for_authenticated_user(self):
        user = User.objects.create_user(username='problem-list-user', password='test-password')
        self.client.force_login(user)

        response = self.client.get('/problems/')

        self.assertEqual(response.status_code, 200)

    def test_problem_group_list_redirects_anonymous_user_to_login(self):
        response = self.client.get('/problems/basic/')

        self.assertRedirects(response, '/accounts/login/?next=/problems/basic/', fetch_redirect_response=False)


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class ProblemGroupNavigationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='problem-group-user', password='test-password')
        self.client.force_login(self.user)
        self.basic_group = create_problem_group(name='basic', full_name='기초')
        self.practice_group = create_problem_group(name='practice', full_name='연습')
        self.basic_problem = create_problem(
            code='basic-navigation',
            name='기초 탐색',
            group=self.basic_group,
            is_public=True,
        )
        self.practice_problem = create_problem(
            code='practice-navigation',
            name='실전 탐색',
            group=self.practice_group,
            is_public=True,
        )

    def test_problem_root_shows_group_cards(self):
        response = self.client.get(reverse('problem_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '기초')
        self.assertContains(response, '연습')
        self.assertContains(response, reverse('problem_group_list', args=('basic',)))
        self.assertContains(response, reverse('problem_group_list', args=('practice',)))

    def test_group_slug_is_used_in_url_and_korean_name_is_displayed(self):
        stack_group = create_problem_group(name='stack', full_name='스택')
        stack_problem = create_problem(
            code='stack-navigation', name='스택 탐색', group=stack_group, is_public=True,
        )

        catalog_response = self.client.get(reverse('problem_list'))
        self.assertEqual(catalog_response.status_code, 200)
        self.assertContains(catalog_response, '스택')
        self.assertContains(catalog_response, reverse('problem_group_list', args=('stack',)))

        group_response = self.client.get(reverse('problem_group_list', args=('stack',)))
        self.assertEqual(group_response.status_code, 200)
        self.assertContains(group_response, stack_problem.name)

    def test_group_page_only_shows_problems_in_selected_group(self):
        response = self.client.get(reverse('problem_group_list', args=('basic',)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.basic_problem.name)
        self.assertNotContains(response, self.practice_problem.name)
        self.assertContains(response, '← 전체 문제 분류')
        self.assertNotContains(response, 'id="problem-group"')

    def test_legacy_group_id_does_not_override_path_group(self):
        response = self.client.get(
            reverse('problem_group_list', args=('basic',)),
            {'groupId': 'bfs'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.basic_problem.name)
        self.assertNotContains(response, self.practice_problem.name)

    def test_legacy_category_query_redirects_to_group_url(self):
        response = self.client.get(reverse('problem_list'), {
            'category': self.basic_problem.group_id,
            'search': '탐색',
        })

        self.assertRedirects(
            response,
            reverse('problem_group_list', args=('basic',)) + '?search=%ED%83%90%EC%83%89',
            fetch_redirect_response=False,
        )

    def test_unknown_problem_group_returns_not_found(self):
        response = self.client.get('/problems/not-a-group/')

        self.assertEqual(response.status_code, 404)
