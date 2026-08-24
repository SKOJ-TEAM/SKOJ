from django import forms
from django.contrib import admin
from django.db import transaction

from judge.models import DifficultyCluster, Problem, ProfileGamification, PromotionAttempt, \
    PromotionAttemptProblem, PromotionExam


class PromotionExamForm(forms.ModelForm):
    problems = forms.ModelMultipleChoiceField(
        queryset=Problem.objects.filter(is_contest_problem=False).order_by('code'), required=False, label='승급 문제',
    )

    class Meta:
        model = PromotionExam
        fields = ('title', 'source_tier', 'is_active', 'problems')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['problems'].initial = self.instance.problems.all()

@admin.register(DifficultyCluster)
class DifficultyClusterAdmin(admin.ModelAdmin):
    fields = ('tier', 'problem_type', 'required_solve_count', 'ranking_weight', 'order', 'is_active')
    list_display = ('problem_type', 'tier', 'required_solve_count', 'ranking_weight', 'order', 'is_active')
    list_filter = ('tier', 'is_active')
    ordering = ('tier', 'order', 'problem_type__full_name')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        transaction.on_commit(schedule_gamification_rebuild)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        transaction.on_commit(schedule_gamification_rebuild)

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        transaction.on_commit(schedule_gamification_rebuild)


@admin.register(PromotionExam)
class PromotionExamAdmin(admin.ModelAdmin):
    form = PromotionExamForm
    list_display = ('title', 'source_tier', 'target_tier_display', 'problem_count', 'is_active')
    list_filter = ('source_tier', 'is_active')

    def target_tier_display(self, obj):
        return obj.target_tier

    def problem_count(self, obj):
        return obj.problems.count()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        selected = form.cleaned_data['problems']
        form.instance.problems.exclude(pk__in=selected).update(promotion_exam=None, promotion_order=0)
        selected.update(gamification_cluster=None, promotion_exam=form.instance)
        transaction.on_commit(schedule_gamification_rebuild)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        transaction.on_commit(schedule_gamification_rebuild)

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        transaction.on_commit(schedule_gamification_rebuild)


def schedule_gamification_rebuild():
    from judge.tasks import rebuild_all_gamification
    rebuild_all_gamification.delay()


class PromotionAttemptProblemInline(admin.TabularInline):
    model = PromotionAttemptProblem
    extra = 0
    can_delete = False
    readonly_fields = ('problem', 'order')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PromotionAttempt)
class PromotionAttemptAdmin(admin.ModelAdmin):
    list_display = ('profile', 'source_tier', 'target_tier', 'unlocked_at', 'completed_at')
    list_filter = ('source_tier', 'target_tier', 'completed_at')
    search_fields = ('profile__user__username',)
    readonly_fields = ('profile', 'exam', 'source_tier', 'target_tier', 'unlocked_at', 'completed_at')
    inlines = (PromotionAttemptProblemInline,)

    def has_add_permission(self, request):
        return False


@admin.register(ProfileGamification)
class ProfileGamificationAdmin(admin.ModelAdmin):
    list_display = ('profile', 'current_tier', 'weighted_score', 'diamond_solved', 'gold_solved',
                    'bronze_solved', 'tier_updated_at')
    list_filter = ('current_tier',)
    search_fields = ('profile__user__username',)
    readonly_fields = ('profile', 'current_tier', 'tier_updated_at', 'weighted_score', 'bronze_solved',
                       'gold_solved', 'diamond_solved', 'score_updated_at')

    def has_add_permission(self, request):
        return False
