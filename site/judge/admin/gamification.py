import json
import re
from collections import defaultdict

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse

from judge.models import DifficultyCluster, Problem, ProfileGamification, PromotionAttempt, \
    PromotionAttemptProblem, PromotionExam, Tier


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
    change_form_template = 'admin/judge/promotionexam/change_form.html'
    fields = ('title', 'source_tier', 'is_active')
    list_display = ('title', 'source_tier', 'target_tier_display', 'problem_count', 'is_active')
    list_filter = ('source_tier', 'is_active')

    def get_urls(self):
        return [
            path(
                '<int:exam_id>/problem-manager/',
                self.admin_site.admin_view(self.problem_manager_view),
                name='judge_promotionexam_problem_manager',
            ),
            path(
                '<int:exam_id>/problem-manager/update/',
                self.admin_site.admin_view(self.update_problems_view),
                name='judge_promotionexam_problem_manager_update',
            ),
        ] + super().get_urls()

    def target_tier_display(self, obj):
        return dict(Tier.choices).get(obj.target_tier, obj.target_tier)
    target_tier_display.short_description = '승급 티어'

    def problem_count(self, obj):
        return obj.problems.count()
    problem_count.short_description = '문제 수'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        transaction.on_commit(schedule_gamification_rebuild)

    def problem_manager_view(self, request, exam_id):
        exam = get_object_or_404(PromotionExam, pk=exam_id)
        if not self.has_change_permission(request, exam):
            raise PermissionDenied

        problems = Problem.objects.filter(is_contest_problem=False).filter(
            Q(promotion_exam__isnull=True) | Q(promotion_exam=exam),
        ).select_related('group').order_by('group__full_name', 'code')
        selected_ids = set(exam.problems.values_list('id', flat=True))
        selected_lookup = defaultdict(bool, {problem_id: True for problem_id in selected_ids})
        problem_tree = {'name': 'root', 'is_dir': True, 'children': []}

        for problem in problems:
            group_name = problem.group.full_name if problem.group else '기타'
            names = re.sub(r'/+', '/', f'{group_name}/{problem.name}').strip('/').split('/')
            current_level = problem_tree['children']
            for index, part in enumerate(names):
                existing = next(
                    (node for node in current_level if node['name'] == part and node.get('is_dir', False)),
                    None,
                )
                if existing:
                    current_level = existing['children']
                    continue

                node = {'name': part, 'is_dir': index < len(names) - 1}
                if node['is_dir']:
                    node['children'] = []
                    current_level.append(node)
                    current_level = node['children']
                else:
                    node.update(id=problem.id, name=problem.name, selected=selected_lookup[problem.id])
                    current_level.append(node)

        return render(request, 'admin/judge/contest/problem_tree_manager.html', {
            'problems': json.dumps(problem_tree),
            'page_title': f'{exam.title} 문제 관리',
            'page_description': '승급전에 포함할 문제를 선택하세요',
            'update_url': reverse('admin:judge_promotionexam_problem_manager_update', args=(exam.pk,)),
        })

    def update_problems_view(self, request, exam_id):
        exam = get_object_or_404(PromotionExam, pk=exam_id)
        if not self.has_change_permission(request, exam):
            raise PermissionDenied
        if request.method != 'POST':
            return JsonResponse({'message': 'POST 요청만 허용됩니다.'}, status=405)

        try:
            selected_items = json.loads(request.POST.get('selected_items', '{}'))
            if not isinstance(selected_items, dict):
                raise ValueError
            requested_ids = [int(problem_id) for problem_id, selected in selected_items.items() if selected is True]
        except (TypeError, ValueError, json.JSONDecodeError):
            return JsonResponse({'message': '잘못된 문제 선택 데이터입니다.'}, status=400)

        eligible_ids = set(Problem.objects.filter(
            Q(promotion_exam__isnull=True) | Q(promotion_exam=exam),
            pk__in=requested_ids,
            is_contest_problem=False,
        ).values_list('pk', flat=True))
        ordered_ids = [problem_id for problem_id in requested_ids if problem_id in eligible_ids]

        with transaction.atomic():
            exam.problems.exclude(pk__in=ordered_ids).update(promotion_exam=None, promotion_order=0)
            for order, problem_id in enumerate(ordered_ids):
                Problem.objects.filter(pk=problem_id).update(
                    gamification_cluster=None,
                    promotion_exam=exam,
                    promotion_order=order,
                )
            transaction.on_commit(schedule_gamification_rebuild)

        return JsonResponse({'message': '승급전 문제를 저장했습니다.', 'selected_count': len(ordered_ids)})

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
