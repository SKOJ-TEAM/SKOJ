import json

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

    def test_authenticated_user_sees_bronze_tier(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('gamification_ranking'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bronze')

    def test_only_diamond_profiles_appear_in_ranking(self):
        diamond = User.objects.create_user(username='diamond-user')
        ProfileGamification.objects.filter(profile=diamond.profile).update(
            current_tier=Tier.DIAMOND,
            weighted_score=20,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('gamification_ranking'))
        self.assertNotContains(response, 'diamond-user')  # no cohort membership means no cohort ranking

    def test_admin_can_view_global_diamond_ranking_with_difficulty_tiebreak(self):
        admin = User.objects.create_superuser(username='ranking-admin', email='admin@example.com', password='pw')
        gold_heavy = User.objects.create_user(username='gold-heavy')
        diamond_heavy = User.objects.create_user(username='diamond-heavy')
        ProfileGamification.objects.filter(profile=gold_heavy.profile).update(
            current_tier=Tier.DIAMOND, weighted_score=20, gold_solved=5, diamond_solved=1,
        )
        ProfileGamification.objects.filter(profile=diamond_heavy.profile).update(
            current_tier=Tier.DIAMOND, weighted_score=20, gold_solved=1, diamond_solved=2,
        )

        self.client.force_login(admin)
        response = self.client.get(reverse('gamification_ranking'), {'scope': 'all'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'gold-heavy')
        self.assertContains(response, 'diamond-heavy')
        self.assertLess(
            response.content.index(b'diamond-heavy'),
            response.content.index(b'gold-heavy'),
        )


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
        self.assertNotContains(response, 'name="problems"')

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
