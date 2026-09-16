from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Tier(models.TextChoices):
    BRONZE = 'bronze', _('브론즈')
    SILVER = 'silver', _('실버')
    GOLD = 'gold', _('골드')
    DIAMOND = 'diamond', _('다이아몬드')
    MASTER = 'master', _('마스터')

    @classmethod
    def next(cls, tier):
        return {
            cls.BRONZE: cls.SILVER,
            cls.SILVER: cls.GOLD,
            cls.GOLD: cls.DIAMOND,
            cls.DIAMOND: cls.MASTER,
        }.get(tier)


class DifficultyCluster(models.Model):
    tier = models.CharField(max_length=10, choices=Tier.choices, db_index=True, verbose_name=_('티어'))
    problem_group = models.ForeignKey('ProblemGroup', on_delete=models.PROTECT, related_name='difficulty_clusters',
                                      verbose_name=_('문제 그룹'))
    required_solve_count = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], verbose_name=_('승급 기준 풀이 수'),
    )
    ranking_weight = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], verbose_name=_('랭킹 가중치'),
    )
    order = models.PositiveIntegerField(default=0, verbose_name=_('표시 순서'))
    is_active = models.BooleanField(default=True, verbose_name=_('활성화'))

    def __str__(self):
        return '%s · %s' % (self.get_tier_display(), self.problem_group.full_name)

    class Meta:
        ordering = ('tier', 'order', 'problem_group__full_name')
        constraints = [
            models.UniqueConstraint(fields=('problem_group',), name='unique_gamification_problem_group_cluster'),
            models.CheckConstraint(check=Q(required_solve_count__gte=1), name='positive_cluster_required_solves'),
            models.CheckConstraint(check=Q(ranking_weight__gte=1), name='positive_cluster_ranking_weight'),
        ]
        verbose_name = _('난이도 클러스터')
        verbose_name_plural = _('난이도 클러스터')


class ChallengeExam(models.Model):
    SOURCE_TIER_CHOICES = (
        (Tier.BRONZE, _('브론즈 → 실버')),
        (Tier.SILVER, _('실버 → 골드')),
        (Tier.GOLD, _('골드 → 다이아몬드')),
        (Tier.DIAMOND, _('다이아몬드 → 마스터')),
    )

    title = models.CharField(max_length=100, verbose_name=_('제목'))
    source_tier = models.CharField(max_length=10, choices=SOURCE_TIER_CHOICES, db_index=True,
                                   verbose_name=_('출발 티어'))
    is_active = models.BooleanField(default=True, verbose_name=_('활성화'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('생성 시각'))

    @property
    def target_tier(self):
        return Tier.next(self.source_tier)

    def clean(self):
        super().clean()
        if self.is_active and ChallengeExam.objects.exclude(pk=self.pk).filter(
                source_tier=self.source_tier, is_active=True).exists():
            raise ValidationError({'is_active': _('출발 티어별로 하나의 승급전만 활성화할 수 있습니다.')})

    def __str__(self):
        return '%s (%s)' % (self.title, self.get_source_tier_display())

    class Meta:
        ordering = ('source_tier', '-is_active', '-created_at')
        verbose_name = _('승급전')
        verbose_name_plural = _('승급전')


class ProfileGamification(models.Model):
    profile = models.OneToOneField('Profile', on_delete=models.CASCADE, related_name='gamification',
                                   verbose_name=_('사용자 프로필'))
    current_tier = models.CharField(max_length=10, choices=Tier.choices, default=Tier.BRONZE,
                                    db_index=True, verbose_name=_('현재 티어'))
    tier_updated_at = models.DateTimeField(default=timezone.now, verbose_name=_('티어 변경 시각'))
    weighted_score = models.PositiveIntegerField(default=0, db_index=True, verbose_name=_('가중 점수'))
    bronze_solved = models.PositiveIntegerField(default=0, verbose_name=_('브론즈 풀이 수'))
    silver_solved = models.PositiveIntegerField(default=0, verbose_name=_('실버 풀이 수'))
    gold_solved = models.PositiveIntegerField(default=0, verbose_name=_('골드 풀이 수'))
    diamond_solved = models.PositiveIntegerField(default=0, verbose_name=_('다이아몬드 풀이 수'))
    master_solved = models.PositiveIntegerField(default=0, verbose_name=_('마스터 풀이 수'))
    score_updated_at = models.DateTimeField(default=timezone.now, verbose_name=_('점수 갱신 시각'))

    def __str__(self):
        return '%s · %s' % (self.profile.username, self.get_current_tier_display())

    class Meta:
        ordering = ('-weighted_score', '-master_solved', '-diamond_solved', '-gold_solved', '-silver_solved',
                    '-bronze_solved', 'profile_id')
        verbose_name = _('사용자 티어')
        verbose_name_plural = _('사용자 티어')


class ChallengeAttempt(models.Model):
    profile = models.ForeignKey('Profile', on_delete=models.CASCADE, related_name='challenge_attempts',
                                verbose_name=_('사용자 프로필'))
    exam = models.ForeignKey(ChallengeExam, on_delete=models.PROTECT, related_name='attempts',
                             verbose_name=_('승급전'))
    source_tier = models.CharField(max_length=10, choices=Tier.choices, verbose_name=_('출발 티어'))
    target_tier = models.CharField(max_length=10, choices=Tier.choices, verbose_name=_('목표 티어'))
    unlocked_at = models.DateTimeField(default=timezone.now, verbose_name=_('해금 시각'))
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_('완료 시각'))
    problems = models.ManyToManyField('Problem', through='ChallengeAttemptProblem', related_name='+')

    @property
    def is_completed(self):
        return self.completed_at is not None

    def __str__(self):
        return '%s · %s → %s' % (self.profile.username, self.source_tier, self.target_tier)

    class Meta:
        ordering = ('-unlocked_at',)
        constraints = [
            models.UniqueConstraint(fields=('profile', 'source_tier'), name='unique_profile_source_tier_attempt'),
        ]
        verbose_name = _('승급 기록')
        verbose_name_plural = _('승급 기록')


class ChallengeAttemptProblem(models.Model):
    attempt = models.ForeignKey(
        ChallengeAttempt, on_delete=models.CASCADE, related_name='snapshot_problems', verbose_name=_('승급 기록'),
    )
    problem = models.ForeignKey('Problem', on_delete=models.PROTECT, related_name='+', verbose_name=_('문제'))
    order = models.PositiveIntegerField(default=0, verbose_name=_('표시 순서'))

    class Meta:
        ordering = ('order', 'id')
        constraints = [
            models.UniqueConstraint(fields=('attempt', 'problem'), name='unique_attempt_snapshot_problem'),
        ]
        verbose_name = _('승급전 문제 스냅샷')
        verbose_name_plural = _('승급전 문제 스냅샷')
