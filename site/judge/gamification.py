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
        gamification_cluster__isnull=False,
        gamification_cluster__is_active=True,
        submission__user=profile,
        submission__result='AC',
        submission__points__gte=F('points'),
    ).select_related('gamification_cluster').distinct()


def recalculate_profile_score(profile):
    gamification = get_or_create_gamification(profile)
    solved = list(solved_cluster_problems(profile).values_list(
        'gamification_cluster__tier', 'gamification_cluster__ranking_weight',
    ))
    counts = {tier: 0 for tier in Tier.values}
    weighted_score = 0
    for tier, weight in solved:
        counts[tier] += 1
        weighted_score += weight

    ProfileGamification.objects.filter(pk=gamification.pk).update(
        weighted_score=weighted_score,
        bronze_solved=counts[Tier.BRONZE],
        gold_solved=counts[Tier.GOLD],
        diamond_solved=counts[Tier.DIAMOND],
        score_updated_at=timezone.now(),
    )
    gamification.refresh_from_db()
    return gamification


def get_tier_progress(profile, tier=None):
    gamification = get_or_create_gamification(profile)
    tier = tier or gamification.current_tier
    return list(DifficultyCluster.objects.filter(tier=tier, is_active=True).select_related('problem_group').annotate(
        solved_count=Count('problems', filter=Q(
            problems__is_public=True,
            problems__is_contest_problem=False,
            problems__submission__user=profile,
            problems__submission__result='AC',
            problems__submission__points__gte=F('problems__points'),
        ), distinct=True),
    ).order_by('order', 'problem_group__full_name'))


def is_eligible_for_promotion(profile, gamification=None):
    gamification = gamification or get_or_create_gamification(profile)
    if gamification.current_tier == Tier.DIAMOND:
        return False
    progress = get_tier_progress(profile, gamification.current_tier)
    return bool(progress) and all(cluster.solved_count >= cluster.required_solve_count for cluster in progress)


@transaction.atomic
def unlock_promotion_attempt(profile):
    gamification = ProfileGamification.objects.select_for_update().get(profile=profile)
    if gamification.current_tier == Tier.DIAMOND or not is_eligible_for_promotion(profile, gamification):
        return None

    existing = PromotionAttempt.objects.filter(
        profile=profile, source_tier=gamification.current_tier,
    ).first()
    if existing is not None:
        return existing

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
    PromotionAttemptProblem.objects.bulk_create([
        PromotionAttemptProblem(attempt=attempt, problem=problem, order=problem.promotion_order)
        for problem in problems
    ])
    return attempt


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


def can_access_promotion_problem(profile, problem):
    return PromotionAttemptProblem.objects.filter(attempt__profile=profile, problem=problem).exists()
