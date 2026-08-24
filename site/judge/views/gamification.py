from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from judge.gamification import get_active_attempt, get_attempt_solved_problem_ids, get_tier_progress, \
    is_eligible_for_promotion, sync_profile_gamification
from judge.models import Cohort, ProfileGamification, PromotionAttempt, Tier
from judge.utils.views import TitleMixin


class RankingView(LoginRequiredMixin, TitleMixin, TemplateView):
    title = 'Ranking'
    template_name = 'gamification/ranking.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.request.profile
        gamification = sync_profile_gamification(profile)
        progress = get_tier_progress(profile, gamification.current_tier)
        attempt = get_active_attempt(profile, gamification)
        if attempt is None:
            attempt = PromotionAttempt.objects.filter(profile=profile).order_by('-unlocked_at').first()

        attempt_problems = []
        if attempt is not None:
            solved_ids = get_attempt_solved_problem_ids(attempt)
            attempt_problems = [
                {'problem': item.problem, 'solved': item.problem_id in solved_ids}
                for item in attempt.snapshot_problems.select_related('problem').all()
            ]

        cohort = None
        scope = 'cohort'
        if self.request.user.is_staff or self.request.user.is_superuser:
            scope = self.request.GET.get('scope', 'cohort')
            cohort_id = self.request.GET.get('cohort')
            if scope != 'all':
                cohort = Cohort.objects.filter(pk=cohort_id).first() if cohort_id else (
                    profile.training_class.cohort if profile.training_class_id else Cohort.objects.first()
                )
        elif profile.training_class_id:
            cohort = profile.training_class.cohort

        rankings = ProfileGamification.objects.filter(
            current_tier=Tier.DIAMOND,
            profile__is_unlisted=False,
            profile__user__is_active=True,
            profile__user__is_staff=False,
            profile__user__is_superuser=False,
        ).select_related('profile__user', 'profile__training_class__cohort', 'profile__training_class__campus')
        if scope != 'all':
            rankings = rankings.filter(profile__training_class__cohort=cohort) if cohort else rankings.none()
        rankings = list(rankings.order_by(
            '-weighted_score', '-diamond_solved', '-gold_solved', '-bronze_solved', 'profile_id',
        ))
        for index, ranking in enumerate(rankings, start=1):
            ranking.rank = index

        context.update({
            'gamification': gamification,
            'tier_progress': progress,
            'promotion_eligible': is_eligible_for_promotion(profile, gamification),
            'promotion_attempt': attempt,
            'promotion_problems': attempt_problems,
            'rankings': rankings,
            'ranking_scope': scope,
            'selected_cohort': cohort,
            'cohorts': Cohort.objects.all(),
            'is_admin_view': self.request.user.is_staff or self.request.user.is_superuser,
        })
        return context
