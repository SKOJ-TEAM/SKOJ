from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Min, Q
from django.http import HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import DetailView, ListView

from judge.models import AlgorithmGuide, ProblemType


LEGACY_GUIDE_SLUGS = {
    '시간복잡도': 'time-complexity',
    '연결리스트': 'array-linked-list',
    '누적합': 'prefix-sum',
    '재귀': 'recursion',
    '스택': 'stack',
    '큐': 'queue',
    '덱': 'deque',
    '해시': 'hash',
    '브루트포스': 'brute-force',
    '백트래킹': 'backtracking',
    '정렬': 'sorting',
    '이분탐색': 'binary-search',
    '트리': 'tree',
    '이진 검색 트리': 'binary-search-tree',
    '힙': 'heap',
    '트라이': 'trie',
    '그래프': 'graph',
    'DFS': 'dfs',
    'BFS': 'bfs',
    '위상정렬': 'topological-sort',
    '유니온 파인드': 'union-find',
    '그리디': 'greedy',
    '크루스칼': 'kruskal',
    '다익스트라': 'dijkstra',
    '다이나믹 프로그래밍': 'dynamic-programming',
    '플로이드': 'floyd',
    'KMP': 'kmp',
}

def redirect_legacy_slug(problem_type, view_name, *args):
    canonical_slug = LEGACY_GUIDE_SLUGS.get(problem_type)
    if canonical_slug is None:
        return None
    return HttpResponsePermanentRedirect(reverse(view_name, args=(canonical_slug, *args)))


class GuideTagList(LoginRequiredMixin, ListView):
    template_name = 'guide/tag_list.html'
    context_object_name = 'guide_tags'

    def get_queryset(self):
        return ProblemType.objects.filter(
            algorithm_guides__is_published=True,
        ).annotate(
            guide_order=Min(
                'algorithm_guides__order',
                filter=Q(algorithm_guides__is_published=True),
            ),
        ).order_by('guide_order', 'full_name', 'name')

class GuideList(LoginRequiredMixin, ListView):
    template_name = 'guide/guide_list.html'
    context_object_name = 'guides'

    def dispatch(self, request, *args, **kwargs):
        redirect_response = redirect_legacy_slug(kwargs['problem_type'], 'guide_list')
        if redirect_response is not None:
            return redirect_response
        self.guide_tag = get_object_or_404(ProblemType, name=kwargs['problem_type'])
        if self.guide_tag.name != kwargs['problem_type']:
            return HttpResponsePermanentRedirect(reverse('guide_list', args=(self.guide_tag.name,)))
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return self.guide_tag.algorithm_guides.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['guide_tag'] = self.guide_tag
        return context


class GuideDetail(LoginRequiredMixin, DetailView):
    template_name = 'guide/guide_detail.html'
    context_object_name = 'guide'

    def dispatch(self, request, *args, **kwargs):
        redirect_response = redirect_legacy_slug(kwargs['problem_type'], 'guide_detail', kwargs['pk'])
        if redirect_response is not None:
            return redirect_response
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return AlgorithmGuide.objects.filter(
            is_published=True,
            problem_type__name=self.kwargs['problem_type'],
        ).select_related('problem_type')
