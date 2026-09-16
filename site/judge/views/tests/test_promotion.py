from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from judge.models import AlgorithmGuide, DifficultyCluster, GuideCompletion, Language, ProblemGroup, \
    ProfileGamification, PromotionAttempt, PromotionExam, Submission, Tier
from judge.models.tests.util import create_problem


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class PromotionViewTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='promotion-view-user')
        self.group = ProblemGroup.objects.create(name='promotion-stack', full_name='스택')
        self.cluster = DifficultyCluster.objects.create(
            tier=Tier.BRONZE, problem_group=self.group, required_solve_count=2, ranking_weight=1,
        )
        self.regular = create_problem(code='promotion-practice', group=self.group, is_public=True, points=10)
        self.second_regular = create_problem(code='promotion-practice2', group=self.group, is_public=True, points=10)
        self.exam = PromotionExam.objects.create(title='실버 승급 시험', source_tier=Tier.BRONZE)
        self.first = create_problem(
            code='promotion-first', name='비밀 승급 문제 하나', group=self.group,
            is_public=False, promotion_exam=self.exam, promotion_order=1, points=10,
        )
        self.second = create_problem(
            code='promotion-second', name='비밀 승급 문제 둘', group=self.group,
            is_public=True, promotion_exam=self.exam, promotion_order=2, points=10,
        )
        self.url = reverse('gamification_promotion')
        self.client.force_login(self.user)

    def solve(self, problem, points=None, result='AC', user=None):
        return Submission.objects.create(
            user=(user or self.user).profile, problem=problem, language=Language.get_python3(),
            status='D', result=result, points=problem.points if points is None else points,
        )

    def unlock(self):
        self.solve(self.regular)
        self.solve(self.second_regular)

    def test_login_is_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, '/accounts/login/?next=/promotion/', fetch_redirect_response=False)
        self.assertNotContains(self.client.get(reverse('home')), '비밀 승급 문제')

    def test_navigation_is_after_problems_and_active(self):
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertLess(content.index('>PROBLEMS</a>'), content.index('>승급전</a>'))
        self.assertLess(content.index('>승급전</a>'), content.index('>RANKING</a>'))
        self.assertContains(response, 'href="/promotion/" class="active" aria-current="page"')
        self.assertContains(response, '<button id="navicon" type="button"')
        self.assertContains(response, 'aria-controls="nav-list" aria-expanded="false"')
        self.assertNotContains(response, 'onclick="toggleMenu()"')

    def test_locked_page_shows_conditions_but_never_exam_names_or_links(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '스택')
        self.assertContains(response, '아직 잠겨 있어요')
        self.assertContains(response, reverse('problem_group_list', args=(self.group.name,)))
        self.assertEqual(response.context_data['tier_progress'][0].solved_count, 0)
        self.assertFalse(response.context_data['promotion_eligible'])
        for problem in (self.first, self.second):
            self.assertNotContains(response, problem.name)
            self.assertNotContains(response, reverse('problem_detail', args=(problem.code,)))
            self.assertFalse(problem.is_accessible_by(self.user))
            self.assertIn(self.client.get(reverse('problem_detail', args=(problem.code,))).status_code, (403, 404))
        self.assertFalse(PromotionAttempt.objects.filter(profile=self.user.profile).exists())

    def test_only_distinct_full_public_regular_solves_count(self):
        self.solve(self.regular, points=5)
        response = self.client.get(self.url)
        self.assertEqual(response.context_data['tier_progress'][0].solved_count, 0)
        self.solve(self.regular)
        self.solve(self.regular)
        self.solve(self.second_regular, result='WA')
        private = create_problem(code='private-practice', group=self.group, is_public=False)
        contest = create_problem(code='contest-practice', group=self.group, is_public=True, is_contest_problem=True)
        for problem in (private, contest, self.first):
            self.solve(problem)
        response = self.client.get(self.url)
        progress = response.context_data['tier_progress'][0]
        self.assertEqual(progress.solved_count, 1)
        self.assertEqual(progress.progress_percent, 50)
        self.assertFalse(response.context_data['promotion_attempt'])
        self.assertNotContains(response, self.first.name)

    def test_every_active_group_is_required(self):
        group = ProblemGroup.objects.create(name='promotion-queue', full_name='큐')
        cluster = DifficultyCluster.objects.create(
            tier=Tier.BRONZE, problem_group=group, required_solve_count=1, ranking_weight=1,
        )
        self.unlock()
        response = self.client.get(self.url)
        self.assertEqual(response.context_data['promotion_completed_groups'], 1)
        self.assertFalse(response.context_data['promotion_attempt'])
        cluster.is_active = False
        cluster.save(update_fields=('is_active',))
        self.assertIsNotNone(self.client.get(self.url).context_data['promotion_attempt'])

    def test_eligible_page_unlocks_and_links_ordered_problems_idempotently(self):
        # bulk_create deliberately bypasses submission signals: visiting the page must synchronize.
        Submission.objects.bulk_create([
            Submission(user=self.user.profile, problem=problem, language=Language.get_python3(),
                       status='D', result='AC', points=problem.points)
            for problem in (self.regular, self.second_regular)
        ])
        self.assertFalse(PromotionAttempt.objects.filter(profile=self.user.profile).exists())
        response = self.client.get(self.url)
        self.assertTrue(response.context_data['promotion_eligible'])
        self.assertContains(response, self.exam.title)
        self.assertLess(response.content.index(self.first.name.encode()), response.content.index(self.second.name.encode()))
        for problem in (self.first, self.second):
            url = reverse('problem_detail', args=(problem.code,))
            self.assertContains(response, 'href="%s"' % url)
            self.assertEqual(self.client.get(url).status_code, 200)
        self.client.get(self.url)
        self.assertEqual(PromotionAttempt.objects.filter(profile=self.user.profile).count(), 1)

    def test_another_users_unlock_does_not_expose_my_exam(self):
        other = get_user_model().objects.create_user(username='other-promotion-user')
        for problem in (self.regular, self.second_regular):
            self.solve(problem, user=other)
        self.assertTrue(PromotionAttempt.objects.filter(profile=other.profile).exists())
        response = self.client.get(self.url)
        self.assertNotContains(response, self.first.name)
        self.assertFalse(self.first.is_accessible_by(self.user))

    def test_pre_unlock_solves_do_not_show_as_completed(self):
        self.solve(self.first)
        self.unlock()
        response = self.client.get(self.url)
        self.assertEqual(response.context_data['promotion_solved_count'], 0)
        self.solve(self.first, points=5)
        self.assertEqual(self.client.get(self.url).context_data['promotion_solved_count'], 0)
        self.solve(self.first)
        response = self.client.get(self.url)
        self.assertEqual(response.context_data['promotion_solved_count'], 1)
        self.assertContains(response, '1 / 2 완료')

    def test_completing_exam_updates_tier_and_next_requirements(self):
        self.unlock()
        self.solve(self.first)
        self.solve(self.second)
        response = self.client.get(self.url)
        self.assertEqual(response.context_data['gamification'].current_tier, Tier.SILVER)
        self.assertEqual(response.context_data['promotion_target_tier'], '골드')
        self.assertIsNotNone(PromotionAttempt.objects.get(profile=self.user.profile).completed_at)
        self.assertNotContains(response, self.first.name)

    def test_unlocked_access_is_preserved_if_conditions_change(self):
        self.unlock()
        self.cluster.required_solve_count = 10
        self.cluster.save(update_fields=('required_solve_count',))
        response = self.client.get(self.url)
        self.assertFalse(response.context_data['promotion_eligible'])
        self.assertContains(response, self.first.name)
        self.assertEqual(self.client.get(reverse('problem_detail', args=(self.first.code,))).status_code, 200)

    def test_eligible_without_active_exam_shows_preparing_message(self):
        self.exam.is_active = False
        self.exam.save(update_fields=('is_active',))
        self.unlock()
        response = self.client.get(self.url)
        self.assertTrue(response.context_data['promotion_eligible'])
        self.assertContains(response, '승급전을 준비 중입니다')
        self.assertNotContains(response, self.first.name)

    def test_eligible_with_empty_exam_shows_preparing_message(self):
        self.exam.problems.update(promotion_exam=None)
        self.unlock()
        response = self.client.get(self.url)
        self.assertTrue(response.context_data['promotion_eligible'])
        self.assertContains(response, '승급전을 준비 중입니다')
        self.assertFalse(PromotionAttempt.objects.filter(profile=self.user.profile).exists())

    def test_no_clusters_does_not_unlock(self):
        self.cluster.delete()
        response = self.client.get(self.url)
        self.assertContains(response, '현재 티어의 승급 조건을 준비 중입니다.')
        self.assertFalse(response.context_data['promotion_eligible'])
        self.assertNotContains(response, self.first.name)

    def test_master_has_no_next_tier_or_locked_exam(self):
        ProfileGamification.objects.filter(profile=self.user.profile).update(current_tier=Tier.MASTER)
        response = self.client.get(self.url)
        self.assertContains(response, '마스터, 모든 승급을 완료했어요')
        self.assertIsNone(response.context_data['promotion_target_tier'])
        self.assertNotContains(response, '아직 잠겨 있어요')
        self.assertNotContains(response, 'id="requirements-heading"')

    def test_final_exam_completion_shows_master_state(self):
        ProfileGamification.objects.filter(profile=self.user.profile).update(current_tier=Tier.DIAMOND)
        self.cluster.tier = Tier.DIAMOND
        self.cluster.save(update_fields=('tier',))
        self.exam.source_tier = Tier.DIAMOND
        self.exam.save(update_fields=('source_tier',))
        self.unlock()
        self.solve(self.first)
        self.solve(self.second)
        response = self.client.get(self.url)
        self.assertEqual(response.context_data['gamification'].current_tier, Tier.MASTER)
        self.assertContains(response, '마스터, 모든 승급을 완료했어요')

    def test_removing_all_unlocked_exam_problems_does_not_promote(self):
        self.unlock()
        self.exam.problems.update(promotion_exam=None)
        response = self.client.get(self.url)
        self.assertContains(response, '승급전 문제를 준비 중입니다.')
        self.assertEqual(response.context_data['gamification'].current_tier, Tier.BRONZE)
        self.assertNotContains(response, self.first.name)

    def test_home_learning_cards_are_off_by_default_without_losing_data(self):
        self.assertFalse(settings.DMOJ_HOME_LEARNING_CARDS_ENABLED)
        guide = AlgorithmGuide.objects.create(
            problem_group=self.group, title='보존할 가이드', content='학습 내용', is_published=True,
        )
        GuideCompletion.objects.create(profile=self.user.profile, guide=guide)
        with patch('judge.gamification.get_guide_progress_context') as guide_context:
            response = self.client.get(reverse('home'))
        guide_context.assert_not_called()
        self.assertNotContains(response, 'id="guide-tab-in-progress"')
        self.assertNotContains(response, 'id="tier-tab-current"')
        self.assertNotContains(response, 'id="tier-panel-promotion"')
        self.assertNotContains(response, 'function activateTab(')
        self.assertContains(response, 'id="recommended-problem"')
        self.assertContains(response, '문제 풀러 가기')
        self.assertContains(response, reverse('gamification_promotion'))
        self.assertTrue(GuideCompletion.objects.filter(profile=self.user.profile, guide=guide).exists())
        self.assertEqual(self.client.get(reverse('guide_tag_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('guide_detail', args=(self.group.name, guide.pk))).status_code, 200)

    def test_home_still_syncs_promotion_when_cards_are_hidden(self):
        Submission.objects.bulk_create([
            Submission(user=self.user.profile, problem=problem, language=Language.get_python3(),
                       status='D', result='AC', points=problem.points)
            for problem in (self.regular, self.second_regular)
        ])
        response = self.client.get(reverse('home'))
        self.assertTrue(PromotionAttempt.objects.filter(profile=self.user.profile).exists())
        self.assertNotContains(response, self.first.name)

    def test_promotion_page_does_not_load_home_only_context(self):
        with patch('judge.gamification.get_random_unsolved_problem') as recommendation, \
                patch('judge.gamification.get_guide_progress_context') as guide_context:
            self.assertEqual(self.client.get(self.url).status_code, 200)
        recommendation.assert_not_called()
        guide_context.assert_not_called()
