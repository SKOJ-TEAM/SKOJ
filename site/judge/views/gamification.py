from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Case, IntegerField, Value, When
from django.views.generic import TemplateView

from judge.gamification import get_challenge_context
from judge.models import ProfileGamification, Tier
from judge.utils.views import TitleMixin


class ChallengeView(LoginRequiredMixin, TitleMixin, TemplateView):
    title = '승급전'
    template_name = 'gamification/challenge.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_challenge_context(self.request.profile))
        return context


class RankingView(LoginRequiredMixin, TitleMixin, TemplateView):
    title = '랭킹'
    template_name = 'gamification/ranking.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rankings = ProfileGamification.objects.filter(
            profile__is_unlisted=False,
            profile__user__is_active=True,
            profile__user__is_staff=False,
            profile__user__is_superuser=False,
        ).select_related(
            'profile__user', 'profile__training_class__cohort', 'profile__training_class__campus',
        ).annotate(tier_order=Case(
            When(current_tier=Tier.MASTER, then=Value(5)),
            When(current_tier=Tier.DIAMOND, then=Value(4)),
            When(current_tier=Tier.GOLD, then=Value(3)),
            When(current_tier=Tier.SILVER, then=Value(2)),
            default=Value(1),
            output_field=IntegerField(),
        ))
        rankings = list(rankings.order_by(
            '-tier_order', '-weighted_score', '-master_solved', '-diamond_solved', '-gold_solved', '-silver_solved',
            '-bronze_solved', 'profile_id',
        ))
        for index, ranking in enumerate(rankings, start=1):
            ranking.rank = index
        own_ranking = next((row for row in rankings if row.profile_id == self.request.profile.pk), None)
        if own_ranking is not None:
            rankings.insert(0, own_ranking)

        context.update({
            'rankings': rankings,
        })
        return context
