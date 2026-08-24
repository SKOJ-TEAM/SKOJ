from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from judge.models.tests.util import create_problem
from judge.views.problem import PROBLEM_GROUP_CATALOG


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
    expected_group_catalog = (
        ('basic', 'Basic'),
        ('practice', 'Practice'),
        ('bruteforce', 'Bruteforce-Guide'),
        ('backtracking', 'BackTracking-Guide'),
        ('dynamic-programming', 'DP-Guide'),
        ('stack', 'Stack-Guide'),
        ('queue', 'Queue-Guide'),
        ('deque', 'Deque-Guide'),
        ('heap', 'Heap-Guide'),
        ('binary-search-tree', 'BST-Guide'),
        ('trie', 'Trie-Guide'),
        ('prefix-sum', 'PrefixSum-Guide'),
        ('dfs', 'DFS-Guide'),
        ('bfs', 'BFS-Guide'),
        ('topological-sort', 'TopoSort-Guide'),
        ('union-find', 'DSU-Guide'),
        ('kruskal', 'MST-Guide'),
        ('dijkstra', 'Dijkstra'),
        ('floyd', 'Floyd-Guide'),
    )

    def setUp(self):
        self.user = User.objects.create_user(username='problem-group-user', password='test-password')
        self.client.force_login(self.user)
        self.basic_problem = create_problem(
            code='basic-navigation',
            name='기초 탐색',
            group='Basic',
            is_public=True,
        )
        self.practice_problem = create_problem(
            code='practice-navigation',
            name='실전 탐색',
            group='Practice',
            is_public=True,
        )

    def test_problem_root_shows_group_cards(self):
        response = self.client.get(reverse('problem_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Basic')
        self.assertContains(response, 'Practice')
        self.assertContains(response, reverse('problem_group_list', args=('basic',)))
        self.assertContains(response, reverse('problem_group_list', args=('practice',)))

    def test_all_catalog_groups_have_cards_urls_and_filtered_lists(self):
        self.assertEqual(
            tuple((item['slug'], item['name']) for item in PROBLEM_GROUP_CATALOG),
            self.expected_group_catalog,
        )

        problems = {
            'Basic': self.basic_problem,
            'Practice': self.practice_problem,
        }
        for index, (_, group_name) in enumerate(self.expected_group_catalog[2:], start=2):
            problems[group_name] = create_problem(
                code='catalog-navigation-%02d' % index,
                name='분류 탐색 %02d' % index,
                group=group_name,
                is_public=True,
            )

        catalog_response = self.client.get(reverse('problem_list'))
        self.assertEqual(catalog_response.status_code, 200)
        for slug, group_name in self.expected_group_catalog:
            with self.subTest(group=group_name, page='catalog'):
                self.assertContains(catalog_response, reverse('problem_group_list', args=(slug,)))

            group_response = self.client.get(reverse('problem_group_list', args=(slug,)))
            with self.subTest(group=group_name, page='filtered-list'):
                self.assertEqual(group_response.status_code, 200)
                self.assertContains(group_response, problems[group_name].name)

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
            {'groupId': 'BFS-Guide'},
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
