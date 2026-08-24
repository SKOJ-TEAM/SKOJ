from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from judge.models import ProfileGamification
from judge.utils.views import TitleMixin


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
        ).select_related('profile__user', 'profile__training_class__cohort', 'profile__training_class__campus')
        rankings = list(rankings.order_by(
            '-weighted_score', '-diamond_solved', '-gold_solved', '-bronze_solved', 'profile_id',
        ))
        for index, ranking in enumerate(rankings, start=1):
            ranking.rank = index

        context.update({
            'rankings': rankings,
        })
        return context
