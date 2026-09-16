from django.contrib.auth.models import User
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from judge.gamification import get_attempt_solved_problem_ids, get_tier_progress, sync_profile_gamification
from judge.models import DifficultyCluster, Language, ProblemGroup, Profile, ProfileGamification, ChallengeAttempt, \
    ChallengeExam, Submission, Tier
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
        )
        self.exam = ChallengeExam.objects.create(title='Silver 승급전', source_tier=Tier.BRONZE)
        self.exam_problem = create_problem(
            code='tierexam', points=10, is_public=True, group=self.problem_group, challenge_exam=self.exam,
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
        attempt = ChallengeAttempt.objects.get(profile=self.profile, source_tier=Tier.BRONZE)

        self.assertEqual(gamification.weighted_score, 3)
        self.assertEqual(gamification.bronze_solved, 1)
        self.assertEqual(progress[0].solved_count, 1)
        self.assertEqual(list(attempt.problems.all()), [self.exam_problem])
        self.assertTrue(self.exam_problem.is_accessible_by(self.users['normal']))

        self.exam_problem.challenge_exam = None
        self.exam_problem.is_public = False
        self.exam_problem.save()
        self.assertTrue(self.exam_problem.is_accessible_by(self.users['normal']))

    def test_challenge_solve_before_unlock_is_not_counted(self):
        earlier_submission = self.create_full_solve(self.exam_problem)
        self.create_full_solve(self.regular_problem)
        attempt = ChallengeAttempt.objects.get(profile=self.profile, source_tier=Tier.BRONZE)

        self.assertNotIn(earlier_submission.problem_id, get_attempt_solved_problem_ids(attempt))
        self.profile.gamification.refresh_from_db()
        self.assertEqual(self.profile.gamification.current_tier, Tier.BRONZE)

        challenge_submission = self.create_full_solve(self.exam_problem)
        self.profile.gamification.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(self.profile.gamification.current_tier, Tier.SILVER)
        self.assertIsNotNone(attempt.completed_at)

        challenge_submission.result = 'WA'
        challenge_submission.points = 0
        challenge_submission.save()
        self.profile.gamification.refresh_from_db()
        self.assertEqual(self.profile.gamification.current_tier, Tier.SILVER)

    def test_every_problem_added_after_unlock_is_required_for_challenge(self):
        self.create_full_solve(self.regular_problem)
        attempt = ChallengeAttempt.objects.get(profile=self.profile, source_tier=Tier.BRONZE)
        added_problem = create_problem(
            code='tierexamadded', points=10, is_public=True, group=self.problem_group,
            challenge_exam=self.exam, challenge_order=1,
        )

        self.create_full_solve(self.exam_problem)
        self.profile.gamification.refresh_from_db()
        attempt.refresh_from_db()

        self.assertEqual(self.profile.gamification.current_tier, Tier.BRONZE)
        self.assertIsNone(attempt.completed_at)
        self.assertSetEqual(set(attempt.problems.all()), {self.exam_problem, added_problem})

        self.create_full_solve(added_problem)
        self.profile.gamification.refresh_from_db()
        attempt.refresh_from_db()

        self.assertEqual(self.profile.gamification.current_tier, Tier.SILVER)
        self.assertIsNotNone(attempt.completed_at)

    def test_five_tier_challenge_order(self):
        self.assertEqual(Tier.next(Tier.BRONZE), Tier.SILVER)
        self.assertEqual(Tier.next(Tier.SILVER), Tier.GOLD)
        self.assertEqual(Tier.next(Tier.GOLD), Tier.DIAMOND)
        self.assertEqual(Tier.next(Tier.DIAMOND), Tier.MASTER)
        self.assertIsNone(Tier.next(Tier.MASTER))

    def test_user_deletion_does_not_recreate_gamification(self):
        self.create_full_solve(self.regular_problem)
        user_id = self.users['normal'].id
        profile_id = self.profile.id

        User.objects.filter(pk=user_id).delete()

        self.assertFalse(User.objects.filter(pk=user_id).exists())
        self.assertFalse(Profile.objects.filter(pk=profile_id).exists())
        self.assertFalse(ProfileGamification.objects.filter(profile_id=profile_id).exists())

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

    def test_multiple_group_problems_are_counted_individually(self):
        second_problem = create_problem(
            code='tierregular2', points=10, is_public=True, group=self.problem_group,
        )
        self.create_full_solve(self.regular_problem)
        self.create_full_solve(second_problem)

        gamification = sync_profile_gamification(self.profile)
        self.assertEqual(gamification.weighted_score, 6)
        self.assertEqual(gamification.bronze_solved, 2)

    def test_contest_problem_in_cluster_group_is_not_counted(self):
        self.regular_problem.is_contest_problem = True
        self.regular_problem.save(update_fields=('is_contest_problem',))
        self.create_full_solve(self.regular_problem)

        gamification = sync_profile_gamification(self.profile)
        self.assertEqual(gamification.weighted_score, 0)
        self.assertEqual(gamification.bronze_solved, 0)

    def test_problem_group_can_belong_to_only_one_cluster(self):
        duplicate = DifficultyCluster(
            tier=Tier.GOLD,
            problem_group=self.problem_group,
            required_solve_count=1,
            ranking_weight=5,
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_all_active_cluster_requirements_are_required(self):
        second_group = ProblemGroup.objects.create(name='tier-stack', full_name='스택')
        DifficultyCluster.objects.create(
            tier=Tier.BRONZE,
            problem_group=second_group,
            required_solve_count=1,
            ranking_weight=5,
        )
        self.create_full_solve(self.regular_problem)
        self.assertFalse(ChallengeAttempt.objects.filter(profile=self.profile).exists())

    def test_rebuild_command_is_repeatable_for_one_profile(self):
        self.create_full_solve(self.regular_problem)
        call_command('rebuild_gamification', '--profile', str(self.profile.id), verbosity=0)
        call_command('rebuild_gamification', '--profile', str(self.profile.id), verbosity=0)
        self.profile.gamification.refresh_from_db()
        self.assertEqual(self.profile.gamification.weighted_score, 3)
        self.assertEqual(ChallengeAttempt.objects.filter(profile=self.profile).count(), 1)
