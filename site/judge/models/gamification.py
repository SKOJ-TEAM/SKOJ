from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Tier(models.TextChoices):
    BRONZE = 'bronze', _('Bronze')
    GOLD = 'gold', _('Gold')
    DIAMOND = 'diamond', _('Diamond')

    @classmethod
    def next(cls, tier):
        return {
            cls.BRONZE: cls.GOLD,
            cls.GOLD: cls.DIAMOND,
        }.get(tier)


class DifficultyCluster(models.Model):
    tier = models.CharField(max_length=10, choices=Tier.choices, db_index=True, verbose_name=_('tier'))
    problem_type = models.ForeignKey('ProblemType', on_delete=models.PROTECT, related_name='difficulty_clusters',
                                     verbose_name=_('problem type'))
    required_solve_count = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], verbose_name=_('required solve count'),
    )
    ranking_weight = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], verbose_name=_('ranking weight'),
    )
    order = models.PositiveIntegerField(default=0, verbose_name=_('display order'))
    is_active = models.BooleanField(default=True, verbose_name=_('active'))

    def __str__(self):
        return '%s · %s' % (self.get_tier_display(), self.problem_type.full_name)

    class Meta:
        ordering = ('tier', 'order', 'problem_type__full_name')
        constraints = [
            models.UniqueConstraint(fields=('tier', 'problem_type'), name='unique_tier_problem_type_cluster'),
            models.CheckConstraint(check=Q(required_solve_count__gte=1), name='positive_cluster_required_solves'),
            models.CheckConstraint(check=Q(ranking_weight__gte=1), name='positive_cluster_ranking_weight'),
        ]
        verbose_name = _('difficulty cluster')
        verbose_name_plural = _('difficulty clusters')


class PromotionExam(models.Model):
    SOURCE_TIER_CHOICES = (
        (Tier.BRONZE, _('Bronze to Gold')),
        (Tier.GOLD, _('Gold to Diamond')),
    )

    title = models.CharField(max_length=100, verbose_name=_('title'))
    source_tier = models.CharField(max_length=10, choices=SOURCE_TIER_CHOICES, db_index=True,
                                   verbose_name=_('source tier'))
    is_active = models.BooleanField(default=True, verbose_name=_('active'))
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def target_tier(self):
        return Tier.next(self.source_tier)

    def clean(self):
        super().clean()
        if self.is_active and PromotionExam.objects.exclude(pk=self.pk).filter(
                source_tier=self.source_tier, is_active=True).exists():
            raise ValidationError({'is_active': _('Only one active promotion exam is allowed per source tier.')})

    def __str__(self):
        return '%s (%s)' % (self.title, self.get_source_tier_display())

    class Meta:
        ordering = ('source_tier', '-is_active', '-created_at')
        verbose_name = _('promotion exam')
        verbose_name_plural = _('promotion exams')


class ProfileGamification(models.Model):
    profile = models.OneToOneField('Profile', on_delete=models.CASCADE, related_name='gamification',
                                   verbose_name=_('profile'))
    current_tier = models.CharField(max_length=10, choices=Tier.choices, default=Tier.BRONZE,
                                    db_index=True, verbose_name=_('current tier'))
    tier_updated_at = models.DateTimeField(default=timezone.now, verbose_name=_('tier updated at'))
    weighted_score = models.PositiveIntegerField(default=0, db_index=True, verbose_name=_('weighted solve score'))
    bronze_solved = models.PositiveIntegerField(default=0, verbose_name=_('bronze solved'))
    gold_solved = models.PositiveIntegerField(default=0, verbose_name=_('gold solved'))
    diamond_solved = models.PositiveIntegerField(default=0, verbose_name=_('diamond solved'))
    score_updated_at = models.DateTimeField(default=timezone.now, verbose_name=_('score updated at'))

    def __str__(self):
        return '%s · %s' % (self.profile.username, self.get_current_tier_display())

    class Meta:
        ordering = ('-weighted_score', '-diamond_solved', '-gold_solved', '-bronze_solved', 'profile_id')
        verbose_name = _('profile gamification')
        verbose_name_plural = _('profile gamification')


class PromotionAttempt(models.Model):
    profile = models.ForeignKey('Profile', on_delete=models.CASCADE, related_name='promotion_attempts',
                                verbose_name=_('profile'))
    exam = models.ForeignKey(PromotionExam, on_delete=models.PROTECT, related_name='attempts',
                             verbose_name=_('promotion exam'))
    source_tier = models.CharField(max_length=10, choices=Tier.choices, verbose_name=_('source tier'))
    target_tier = models.CharField(max_length=10, choices=Tier.choices, verbose_name=_('target tier'))
    unlocked_at = models.DateTimeField(default=timezone.now, verbose_name=_('unlocked at'))
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_('completed at'))
    problems = models.ManyToManyField('Problem', through='PromotionAttemptProblem', related_name='+')

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
        verbose_name = _('promotion attempt')
        verbose_name_plural = _('promotion attempts')


class PromotionAttemptProblem(models.Model):
    attempt = models.ForeignKey(PromotionAttempt, on_delete=models.CASCADE, related_name='snapshot_problems')
    problem = models.ForeignKey('Problem', on_delete=models.PROTECT, related_name='+')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('order', 'id')
        constraints = [
            models.UniqueConstraint(fields=('attempt', 'problem'), name='unique_attempt_snapshot_problem'),
        ]
        verbose_name = _('promotion attempt problem')
        verbose_name_plural = _('promotion attempt problems')
