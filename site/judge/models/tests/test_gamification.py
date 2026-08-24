from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from judge.gamification import get_attempt_solved_problem_ids, get_tier_progress, sync_profile_gamification
from judge.models import DifficultyCluster, Language, ProblemGroup, PromotionAttempt, PromotionExam, Submission, Tier
from judge.models.tests.util import CommonDataMixin, create_problem


class GamificationProgressTestCase(CommonDataMixin, TestCase):
    def setUp(self):
        self.profile = self.users['normal'].profile
        self.problem_group = ProblemGroup.objects.create(name='tier-array', full_name='배열')
        self.cluster = DifficultyCluster.objects.create(
            tier=Tier.BRONZE,
            problem_group=self.problem_group,
            required_solve_count=1,
            ranking_weight=3,
        )
        self.regular_problem = create_problem(
            code='tierregular', points=10, is_public=True, group=self.problem_group,
            gamification_cluster=self.cluster,
        )
        self.exam = PromotionExam.objects.create(title='Gold 승급전', source_tier=Tier.BRONZE)
        self.exam_problem = create_problem(
            code='tierexam', points=10, is_public=True, promotion_exam=self.exam,
        )

    def create_full_solve(self, problem):
        return Submission.objects.create(
            user=self.profile,
            problem=problem,
            language=Language.get_python3(),
            status='D',
            result='AC',
            points=problem.points,
            case_points=1,
            case_total=1,
            judged_date=timezone.now(),
        )

    def test_regular_solve_updates_progress_score_and_unlocks_exam(self):
        self.assertFalse(self.exam_problem.is_accessible_by(self.users['normal']))
        self.create_full_solve(self.regular_problem)

        gamification = self.profile.gamification
        gamification.refresh_from_db()
        progress = get_tier_progress(self.profile)
        attempt = PromotionAttempt.objects.get(profile=self.profile, source_tier=Tier.BRONZE)

        self.assertEqual(gamification.weighted_score, 3)
        self.assertEqual(gamification.bronze_solved, 1)
        self.assertEqual(progress[0].solved_count, 1)
        self.assertEqual(list(attempt.problems.all()), [self.exam_problem])
        self.assertTrue(self.exam_problem.is_accessible_by(self.users['normal']))

        self.exam_problem.promotion_exam = None
        self.exam_problem.is_public = False
        self.exam_problem.save()
        self.assertTrue(self.exam_problem.is_accessible_by(self.users['normal']))

    def test_promotion_solve_before_unlock_is_not_counted(self):
        earlier_submission = self.create_full_solve(self.exam_problem)
        self.create_full_solve(self.regular_problem)
        attempt = PromotionAttempt.objects.get(profile=self.profile, source_tier=Tier.BRONZE)

        self.assertNotIn(earlier_submission.problem_id, get_attempt_solved_problem_ids(attempt))
        self.profile.gamification.refresh_from_db()
        self.assertEqual(self.profile.gamification.current_tier, Tier.BRONZE)

        promotion_submission = self.create_full_solve(self.exam_problem)
        self.profile.gamification.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(self.profile.gamification.current_tier, Tier.GOLD)
        self.assertIsNotNone(attempt.completed_at)

        promotion_submission.result = 'WA'
        promotion_submission.points = 0
        promotion_submission.save()
        self.profile.gamification.refresh_from_db()
        self.assertEqual(self.profile.gamification.current_tier, Tier.GOLD)

    def test_partial_and_duplicate_submissions_count_once(self):
        for points in (5, 10, 10):
            Submission.objects.create(
                user=self.profile,
                problem=self.regular_problem,
                language=Language.get_python3(),
                status='D',
                result='AC',
                points=points,
                case_points=points,
                case_total=10,
            )

        gamification = sync_profile_gamification(self.profile)
        self.assertEqual(gamification.weighted_score, 3)
        self.assertEqual(gamification.bronze_solved, 1)

    def test_problem_cannot_have_regular_and_promotion_roles(self):
        self.exam_problem.gamification_cluster = self.cluster
        with self.assertRaises(ValidationError):
            self.exam_problem.full_clean()

    def test_problem_and_cluster_must_use_same_group(self):
        other_group = ProblemGroup.objects.create(name='other-group', full_name='다른 그룹')
        self.regular_problem.group = other_group
        with self.assertRaises(ValidationError):
            self.regular_problem.full_clean()

    def test_contest_problem_cannot_have_gamification_role(self):
        self.regular_problem.is_contest_problem = True
        with self.assertRaises(ValidationError):
            self.regular_problem.full_clean()

    def test_all_active_cluster_requirements_are_required(self):
        second_group = ProblemGroup.objects.create(name='tier-stack', full_name='스택')
        DifficultyCluster.objects.create(
            tier=Tier.BRONZE,
            problem_group=second_group,
            required_solve_count=1,
            ranking_weight=5,
        )
        self.create_full_solve(self.regular_problem)
        self.assertFalse(PromotionAttempt.objects.filter(profile=self.profile).exists())

    def test_rebuild_command_is_repeatable_for_one_profile(self):
        self.create_full_solve(self.regular_problem)
        call_command('rebuild_gamification', '--profile', str(self.profile.id), verbosity=0)
        call_command('rebuild_gamification', '--profile', str(self.profile.id), verbosity=0)
        self.profile.gamification.refresh_from_db()
        self.assertEqual(self.profile.gamification.weighted_score, 3)
        self.assertEqual(PromotionAttempt.objects.filter(profile=self.profile).count(), 1)
