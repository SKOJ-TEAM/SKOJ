from django.core.validators import RegexValidator
from django.db import migrations, models
import django.db.models.deletion


GROUP_DEFINITIONS = {
    'array-linked-list': ('배열과 연결 리스트', ()),
    'backtracking': ('백트래킹', ('BackTracking-Guide',)),
    'basic': ('기초', ('Basic',)),
    'bfs': ('너비 우선 탐색 (BFS)', ('BFS-Guide',)),
    'binary-search': ('이분 탐색', ()),
    'binary-search-tree': ('이진 검색 트리', ('BST-Guide',)),
    'brute-force': ('브루트포스', ('Bruteforce-Guide',)),
    'deque': ('덱', ('Deque-Guide',)),
    'dfs': ('깊이 우선 탐색 (DFS)', ('DFS-Guide',)),
    'dijkstra': ('다익스트라', ('Dijkstra',)),
    'dynamic-programming': ('동적 계획법', ('DP-Guide',)),
    'floyd': ('플로이드-워셜', ('Floyd-Guide',)),
    'graph': ('그래프', ()),
    'greedy': ('그리디', ()),
    'hash': ('해시', ()),
    'heap': ('힙', ('Heap-Guide',)),
    'kmp': ('KMP 문자열 검색', ()),
    'kruskal': ('최소 신장 트리·크루스칼', ('MST-Guide',)),
    'practice': ('연습', ('Practice',)),
    'prefix-sum': ('누적합', ('PrefixSum-Guide',)),
    'queue': ('큐', ('Queue-Guide',)),
    'recursion': ('재귀', ()),
    'sorting': ('정렬', ()),
    'stack': ('스택', ('Stack-Guide',)),
    'time-complexity': ('시간 복잡도', ()),
    'topological-sort': ('위상 정렬', ('TopoSort-Guide',)),
    'tree': ('트리', ()),
    'trie': ('트라이', ('Trie-Guide',)),
    'union-find': ('유니온 파인드', ('DSU-Guide',)),
}


def unify_problem_taxonomy(apps, schema_editor):
    Problem = apps.get_model('judge', 'Problem')
    ProblemGroup = apps.get_model('judge', 'ProblemGroup')
    ProblemType = apps.get_model('judge', 'ProblemType')
    AlgorithmGuide = apps.get_model('judge', 'AlgorithmGuide')
    DifficultyCluster = apps.get_model('judge', 'DifficultyCluster')

    groups = {}
    for slug, (display_name, legacy_names) in GROUP_DEFINITIONS.items():
        target = ProblemGroup.objects.filter(name=slug).first()
        legacy = ProblemGroup.objects.filter(name__in=legacy_names).first() if legacy_names else None

        if target is None and legacy is not None:
            legacy.name = slug
            legacy.full_name = display_name
            legacy.save(update_fields=('name', 'full_name'))
            target = legacy
        elif target is not None:
            target.full_name = display_name
            target.save(update_fields=('full_name',))
            if legacy is not None and legacy.pk != target.pk:
                Problem.objects.filter(group_id=legacy.pk).update(group_id=target.pk)
                legacy.delete()
        if target is not None:
            groups[slug] = target

    for problem_type in ProblemType.objects.all():
        slug = problem_type.name
        group = groups.get(slug)
        if group is None:
            display_name = GROUP_DEFINITIONS.get(slug, (problem_type.full_name, ()))[0]
            group, _ = ProblemGroup.objects.get_or_create(
                name=slug,
                defaults={'full_name': display_name},
            )
            groups[slug] = group
        AlgorithmGuide.objects.filter(problem_type_id=problem_type.pk).update(problem_group_id=group.pk)
        DifficultyCluster.objects.filter(problem_type_id=problem_type.pk).update(problem_group_id=group.pk)


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0044_translate_gamification_admin'),
    ]

    operations = [
        migrations.AddField(
            model_name='algorithmguide',
            name='problem_group',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='algorithm_guides',
                to='judge.problemgroup',
                verbose_name='문제 그룹',
            ),
        ),
        migrations.AddField(
            model_name='difficultycluster',
            name='problem_group',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='difficulty_clusters',
                to='judge.problemgroup',
                verbose_name='문제 그룹',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='difficultycluster',
            name='unique_tier_problem_type_cluster',
        ),
        migrations.RunPython(unify_problem_taxonomy, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='algorithmguide',
            name='problem_group',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='algorithm_guides',
                to='judge.problemgroup',
                verbose_name='문제 그룹',
            ),
        ),
        migrations.AlterField(
            model_name='difficultycluster',
            name='problem_group',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='difficulty_clusters',
                to='judge.problemgroup',
                verbose_name='문제 그룹',
            ),
        ),
        migrations.RemoveField(model_name='algorithmguide', name='problem_type'),
        migrations.RemoveField(model_name='difficultycluster', name='problem_type'),
        migrations.RemoveField(model_name='problem', name='types'),
        migrations.DeleteModel(name='ProblemType'),
        migrations.AlterModelOptions(
            name='difficultycluster',
            options={
                'ordering': ('tier', 'order', 'problem_group__full_name'),
                'verbose_name': '난이도 클러스터',
                'verbose_name_plural': '난이도 클러스터',
            },
        ),
        migrations.AlterModelOptions(
            name='problemgroup',
            options={
                'ordering': ['full_name'],
                'verbose_name': '문제 그룹',
                'verbose_name_plural': '문제 그룹',
            },
        ),
        migrations.AlterField(
            model_name='problemgroup',
            name='name',
            field=models.CharField(
                help_text='문제 그룹 URL에 사용됩니다. 예: stack',
                max_length=100,
                unique=True,
                validators=[RegexValidator(
                    '^[a-z0-9-]+$',
                    'URL slug는 영문 소문자, 숫자, 하이픈만 사용할 수 있습니다.',
                )],
                verbose_name='URL slug',
            ),
        ),
        migrations.AlterField(
            model_name='problemgroup',
            name='full_name',
            field=models.CharField(
                help_text='사용자 화면에 표시됩니다. 예: 스택',
                max_length=100,
                verbose_name='화면 표시명',
            ),
        ),
        migrations.AlterField(
            model_name='problem',
            name='group',
            field=models.ForeignKey(
                help_text='문제 목록의 분류와 URL에 사용됩니다.',
                on_delete=django.db.models.deletion.CASCADE,
                to='judge.problemgroup',
                verbose_name='문제 그룹',
            ),
        ),
        migrations.AddConstraint(
            model_name='difficultycluster',
            constraint=models.UniqueConstraint(
                fields=('tier', 'problem_group'),
                name='unique_tier_problem_group_cluster',
            ),
        ),
    ]
