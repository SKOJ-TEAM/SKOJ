import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from judge.models import ProfileGamification, PromotionExam, Tier
from judge.models.tests.util import CommonDataMixin, create_problem


User = get_user_model()


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class RankingViewTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ranking-user', password='test-password')

    def test_anonymous_user_is_redirected(self):
        response = self.client.get(reverse('gamification_ranking'))
        self.assertRedirects(
            response,
            '/accounts/login/?next=/ranking/',
            fetch_redirect_response=False,
        )

    def test_ranking_page_only_contains_ranking(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('gamification_ranking'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '전체 사용자 랭킹')
        self.assertNotContains(response, '내 티어')
        self.assertNotContains(response, '<h2>승급전</h2>', html=True)

    def test_all_tiers_appear_in_global_ranking(self):
        diamond = User.objects.create_user(username='diamond-user')
        ProfileGamification.objects.filter(profile=diamond.profile).update(
            current_tier=Tier.DIAMOND,
            weighted_score=20,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('gamification_ranking'))

        self.assertContains(response, 'ranking-user')
        self.assertContains(response, 'diamond-user')
        self.assertContains(response, '브론즈')
        self.assertContains(response, '다이아몬드')

    def test_ranking_uses_difficulty_tiebreak(self):
        gold_heavy = User.objects.create_user(username='gold-heavy')
        diamond_heavy = User.objects.create_user(username='diamond-heavy')
        ProfileGamification.objects.filter(profile=gold_heavy.profile).update(
            current_tier=Tier.DIAMOND, weighted_score=20, gold_solved=5, diamond_solved=1,
        )
        ProfileGamification.objects.filter(profile=diamond_heavy.profile).update(
            current_tier=Tier.DIAMOND, weighted_score=20, gold_solved=1, diamond_solved=2,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('gamification_ranking'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'gold-heavy')
        self.assertContains(response, 'diamond-heavy')
        self.assertLess(
            response.content.index(b'diamond-heavy'),
            response.content.index(b'gold-heavy'),
        )

    def test_ranking_orders_by_tier_before_weighted_score(self):
        bronze = User.objects.create_user(username='high-score-bronze')
        diamond = User.objects.create_user(username='low-score-diamond')
        ProfileGamification.objects.filter(profile=bronze.profile).update(
            current_tier=Tier.BRONZE, weighted_score=100,
        )
        ProfileGamification.objects.filter(profile=diamond.profile).update(
            current_tier=Tier.DIAMOND, weighted_score=1,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('gamification_ranking'))

        self.assertLess(
            response.content.index(b'low-score-diamond'),
            response.content.index(b'high-score-bronze'),
        )


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class HomeGamificationCardTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='home-tier-user', password='test-password')

    def test_anonymous_home_hides_gamification_cards(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<section class="home-dashboard"')
        self.assertNotContains(response, '내 티어')
        self.assertContains(response, 'id="home-theme-toggle"')

    def test_anonymous_home_uses_theme_cookie(self):
        self.client.cookies['site_theme'] = 'dark'

        response = self.client.get(reverse('home'))

        self.assertContains(response, "var theme = 'dark';")

    def test_authenticated_home_shows_tier_and_promotion_cards(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<section class="home-dashboard"')
        self.assertContains(response, '내 티어')
        self.assertContains(response, '<h2>승급전</h2>', html=True)
        self.assertContains(response, reverse('gamification_ranking'))

    def test_authenticated_home_prefers_profile_theme_over_cookie(self):
        self.user.profile.site_theme = 'dark'
        self.user.profile.save(update_fields=('site_theme',))
        self.client.cookies['site_theme'] = 'light'
        self.client.force_login(self.user)

        response = self.client.get(reverse('home'))

        self.assertContains(response, "var theme = 'dark';")

    def test_home_theme_toggle_saves_authenticated_profile_theme(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('set_theme'), {'theme': 'dark'})

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.site_theme, 'dark')


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class PromotionExamProblemManagerTestCase(CommonDataMixin, TestCase):
    def setUp(self):
        self.exam = PromotionExam.objects.create(title='Gold 승급전', source_tier=Tier.BRONZE)
        self.first_problem = create_problem(code='promotion-one', name='첫 번째 문제', is_public=True)
        self.second_problem = create_problem(code='promotion-two', name='두 번째 문제', is_public=True)
        self.contest_problem = create_problem(
            code='promotion-contest', name='대회 문제', is_public=True, is_contest_problem=True,
        )
        self.client.force_login(self.users['superuser'])

    def test_change_page_links_to_problem_manager(self):
        response = self.client.get(reverse('admin:judge_promotionexam_change', args=(self.exam.pk,)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse('admin:judge_promotionexam_problem_manager', args=(self.exam.pk,)),
        )
        self.assertContains(response, '현재 선택된 문제: 0개')
        self.assertNotContains(response, 'name="problems"')

    def test_add_page_saves_exam_then_redirects_to_problem_manager(self):
        add_url = reverse('admin:judge_promotionexam_add')
        add_response = self.client.get(add_url)

        self.assertEqual(add_response.status_code, 200)
        self.assertContains(add_response, '저장 후 문제 관리')

        response = self.client.post(add_url, {
            'title': 'Diamond 승급전',
            'source_tier': Tier.GOLD,
            'is_active': 'on',
            '_manage_problems': '1',
        })

        created_exam = PromotionExam.objects.get(title='Diamond 승급전')
        self.assertRedirects(
            response,
            reverse('admin:judge_promotionexam_problem_manager', args=(created_exam.pk,)),
            fetch_redirect_response=False,
        )

    def test_admin_sidebar_groups_gamification_under_korean_ranking_menu(self):
        ranking_menu = next(item for item in settings.WPADMIN['admin']['custom_menu']
                            if isinstance(item, dict) and item.get('title') == '랭킹')

        self.assertEqual(ranking_menu['icon'], 'fa-trophy')
        self.assertEqual(ranking_menu['model'], 'judge.ProfileGamification')
        self.assertEqual(ranking_menu['children'], [
            'judge.DifficultyCluster',
            'judge.PromotionExam',
            'judge.PromotionAttempt',
        ])
        self.assertEqual(ProfileGamification._meta.verbose_name_plural, '사용자 티어')
        self.assertEqual(PromotionExam._meta.verbose_name_plural, '승급전')

        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '랭킹')
        self.assertContains(response, reverse('admin:judge_profilegamification_changelist'))
        self.assertContains(response, '난이도 클러스터')
        self.assertContains(response, '승급전')
        self.assertContains(response, '승급 기록')

    def test_problem_manager_lists_general_problems_and_excludes_contest_problems(self):
        response = self.client.get(reverse(
            'admin:judge_promotionexam_problem_manager', args=(self.exam.pk,),
        ))

        self.assertEqual(response.status_code, 200)
        problem_tree = json.loads(response.context['problems'])
        nodes = [problem_tree]
        problem_ids = []
        while nodes:
            node = nodes.pop()
            nodes.extend(node.get('children', []))
            if not node.get('is_dir', False):
                problem_ids.append(node['id'])
        self.assertIn(self.first_problem.pk, problem_ids)
        self.assertIn(self.second_problem.pk, problem_ids)
        self.assertNotIn(self.contest_problem.pk, problem_ids)

    def test_problem_manager_updates_exam_assignments(self):
        update_url = reverse('admin:judge_promotionexam_problem_manager_update', args=(self.exam.pk,))
        response = self.client.post(update_url, {
            'selected_items': json.dumps({
                str(self.first_problem.pk): True,
                str(self.second_problem.pk): False,
            }),
        })

        self.assertEqual(response.status_code, 200)
        self.first_problem.refresh_from_db()
        self.second_problem.refresh_from_db()
        self.assertEqual(self.first_problem.promotion_exam, self.exam)
        self.assertIsNone(self.second_problem.promotion_exam)

        response = self.client.post(update_url, {
            'selected_items': json.dumps({
                str(self.first_problem.pk): False,
                str(self.second_problem.pk): True,
            }),
        })

        self.assertEqual(response.status_code, 200)
        self.first_problem.refresh_from_db()
        self.second_problem.refresh_from_db()
        self.assertIsNone(self.first_problem.promotion_exam)
        self.assertEqual(self.second_problem.promotion_exam, self.exam)
