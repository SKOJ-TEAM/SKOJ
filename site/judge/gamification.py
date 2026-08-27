import random
import secrets

from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone

from judge.models import DifficultyCluster, Problem, ProfileGamification, PromotionAttempt, \
    PromotionAttemptProblem, PromotionExam, Submission, Tier


def get_or_create_gamification(profile):
    gamification, _ = ProfileGamification.objects.get_or_create(profile=profile)
    return gamification


def solved_cluster_problems(profile):
    return Problem.objects.filter(
        is_public=True,
        is_contest_problem=False,
        promotion_exam__isnull=True,
        group__difficulty_clusters__is_active=True,
        submission__user=profile,
        submission__result='AC',
        submission__points__gte=F('points'),
    ).distinct()


def recalculate_profile_score(profile):
    gamification = get_or_create_gamification(profile)
    solved = list(solved_cluster_problems(profile).values_list(
        'id', 'group__difficulty_clusters__tier', 'group__difficulty_clusters__ranking_weight',
    ))
    counts = {tier: 0 for tier in Tier.values}
    weighted_score = 0
    for _problem_id, tier, weight in solved:
        counts[tier] += 1
        weighted_score += weight

    ProfileGamification.objects.filter(pk=gamification.pk).update(
        weighted_score=weighted_score,
        bronze_solved=counts[Tier.BRONZE],
        silver_solved=counts[Tier.SILVER],
        gold_solved=counts[Tier.GOLD],
        diamond_solved=counts[Tier.DIAMOND],
        master_solved=counts[Tier.MASTER],
        score_updated_at=timezone.now(),
    )
    gamification.refresh_from_db()
    return gamification


def get_tier_progress(profile, tier=None):
    gamification = get_or_create_gamification(profile)
    tier = tier or gamification.current_tier
    return list(DifficultyCluster.objects.filter(tier=tier, is_active=True).select_related('problem_group').annotate(
        solved_count=Count('problem_group__problem', filter=Q(
            problem_group__problem__is_public=True,
            problem_group__problem__is_contest_problem=False,
            problem_group__problem__promotion_exam__isnull=True,
            problem_group__problem__submission__user=profile,
            problem_group__problem__submission__result='AC',
            problem_group__problem__submission__points__gte=F('problem_group__problem__points'),
        ), distinct=True),
    ).order_by('order', 'problem_group__full_name'))


def is_eligible_for_promotion(profile, gamification=None):
    gamification = gamification or get_or_create_gamification(profile)
    if gamification.current_tier == Tier.MASTER:
        return False
    progress = get_tier_progress(profile, gamification.current_tier)
    return bool(progress) and all(cluster.solved_count >= cluster.required_solve_count for cluster in progress)


def sync_promotion_attempt_problems(attempt):
    exam_problems = list(attempt.exam.problems.order_by('promotion_order', 'id').values_list(
        'id', 'promotion_order',
    ))
    problem_ids = [problem_id for problem_id, _order in exam_problems]
    attempt.snapshot_problems.exclude(problem_id__in=problem_ids).delete()
    existing_ids = set(attempt.snapshot_problems.values_list('problem_id', flat=True))
    PromotionAttemptProblem.objects.bulk_create([
        PromotionAttemptProblem(attempt=attempt, problem_id=problem_id, order=order)
        for problem_id, order in exam_problems if problem_id not in existing_ids
    ])
    for problem_id, order in exam_problems:
        attempt.snapshot_problems.filter(problem_id=problem_id).exclude(order=order).update(order=order)
    return attempt


@transaction.atomic
def unlock_promotion_attempt(profile):
    gamification = ProfileGamification.objects.select_for_update().get(profile=profile)
    if gamification.current_tier == Tier.MASTER or not is_eligible_for_promotion(profile, gamification):
        return None

    existing = PromotionAttempt.objects.filter(
        profile=profile, source_tier=gamification.current_tier,
    ).select_related('exam').first()
    if existing is not None:
        return sync_promotion_attempt_problems(existing)

    exam = PromotionExam.objects.filter(source_tier=gamification.current_tier, is_active=True).first()
    if exam is None:
        return None
    problems = list(exam.problems.order_by('promotion_order', 'id'))
    if not problems:
        return None

    attempt = PromotionAttempt.objects.create(
        profile=profile,
        exam=exam,
        source_tier=gamification.current_tier,
        target_tier=exam.target_tier,
    )
    return sync_promotion_attempt_problems(attempt)


def get_active_attempt(profile, gamification=None):
    gamification = gamification or get_or_create_gamification(profile)
    return PromotionAttempt.objects.filter(
        profile=profile,
        source_tier=gamification.current_tier,
        completed_at__isnull=True,
    ).select_related('exam').first()


def get_attempt_solved_problem_ids(attempt):
    problem_ids = attempt.snapshot_problems.values_list('problem_id', flat=True)
    return set(Submission.objects.filter(
        user=attempt.profile,
        problem_id__in=problem_ids,
        date__gte=attempt.unlocked_at,
        result='AC',
        points__gte=F('problem__points'),
    ).values_list('problem_id', flat=True).distinct())


@transaction.atomic
def complete_promotion_if_ready(profile):
    gamification = ProfileGamification.objects.select_for_update().get(profile=profile)
    attempt = PromotionAttempt.objects.select_for_update().filter(
        profile=profile,
        source_tier=gamification.current_tier,
        completed_at__isnull=True,
    ).first()
    if attempt is None:
        return None
    sync_promotion_attempt_problems(attempt)
    required_ids = set(attempt.snapshot_problems.values_list('problem_id', flat=True))
    if not required_ids or not required_ids.issubset(get_attempt_solved_problem_ids(attempt)):
        return None

    completed_at = timezone.now()
    attempt.completed_at = completed_at
    attempt.save(update_fields=('completed_at',))
    gamification.current_tier = attempt.target_tier
    gamification.tier_updated_at = completed_at
    gamification.save(update_fields=('current_tier', 'tier_updated_at'))
    return attempt


def sync_profile_gamification(profile):
    gamification = recalculate_profile_score(profile)
    completed = complete_promotion_if_ready(profile)
    if completed is not None:
        gamification.refresh_from_db()
    unlock_promotion_attempt(profile)
    return gamification


def get_profile_dashboard_context(profile):
    gamification = sync_profile_gamification(profile)
    progress = get_tier_progress(profile, gamification.current_tier)
    attempt = get_active_attempt(profile, gamification)
    attempt_problems = []
    if attempt is not None:
        solved_ids = get_attempt_solved_problem_ids(attempt)
        attempt_problems = [
            {'problem': item.problem, 'solved': item.problem_id in solved_ids}
            for item in attempt.snapshot_problems.select_related('problem').all()
        ]
    return {
        'gamification': gamification,
        'tier_progress': progress,
        'promotion_eligible': is_eligible_for_promotion(profile, gamification),
        'promotion_attempt': attempt,
        'promotion_problems': attempt_problems,
        'recommended_problem': get_random_unsolved_problem(profile),
        'recommendation_nonce': secrets.token_urlsafe(8),
    }


def get_random_unsolved_problem(profile):
    solved_problem_ids = Submission.objects.filter(
        user=profile,
        result='AC',
        points=F('problem__points'),
    ).values_list('problem_id', flat=True)
    candidates = Problem.objects.filter(
        is_public=True,
        is_contest_problem=False,
        promotion_exam__isnull=True,
    ).exclude(id__in=solved_problem_ids)
    candidate_ids = list(candidates.values_list('id', flat=True))
    if not candidate_ids:
        return None
    return candidates.select_related('group').get(pk=random.choice(candidate_ids))


def can_access_promotion_problem(profile, problem):
    return PromotionAttemptProblem.objects.filter(attempt__profile=profile, problem=problem).exists()
