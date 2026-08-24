from django.db import migrations


CURRICULUM_SLUGS = (
    'time-complexity',
    'array-linked-list',
    'prefix-sum',
    'recursion',
    'stack',
    'queue',
    'deque',
    'hash',
    'brute-force',
    'backtracking',
    'sorting',
    'binary-search',
    'tree',
    'binary-search-tree',
    'heap',
    'trie',
    'graph',
    'dfs',
    'bfs',
    'topological-sort',
    'union-find',
    'greedy',
    'kruskal',
    'dijkstra',
    'dynamic-programming',
    'floyd',
    'kmp',
)


def apply_prefix_sum_and_curriculum(apps, schema_editor):
    ProblemType = apps.get_model('judge', 'ProblemType')
    AlgorithmGuide = apps.get_model('judge', 'AlgorithmGuide')

    prefix_sum = ProblemType.objects.filter(name='누적합').first()
    if prefix_sum is None:
        prefix_sum = ProblemType.objects.filter(name='prefix-sum').first()
    if prefix_sum is not None:
        prefix_sum.name = 'prefix-sum'
        prefix_sum.full_name = 'Prefix Sum'
        prefix_sum.save(update_fields=('name', 'full_name'))

    for order, slug in enumerate(CURRICULUM_SLUGS, start=1):
        problem_type = ProblemType.objects.filter(name=slug).first()
        if problem_type is not None:
            AlgorithmGuide.objects.filter(problem_type_id=problem_type.pk).update(order=order)


def restore_before_prefix_sum(apps, schema_editor):
    ProblemType = apps.get_model('judge', 'ProblemType')
    AlgorithmGuide = apps.get_model('judge', 'AlgorithmGuide')

    for order, slug in enumerate((slug for slug in CURRICULUM_SLUGS if slug != 'prefix-sum'), start=1):
        problem_type = ProblemType.objects.filter(name=slug).first()
        if problem_type is not None:
            AlgorithmGuide.objects.filter(problem_type_id=problem_type.pk).update(order=order)

    prefix_sum = ProblemType.objects.filter(name='prefix-sum').first()
    if prefix_sum is not None:
        AlgorithmGuide.objects.filter(problem_type_id=prefix_sum.pk).update(order=16)
        prefix_sum.name = '누적합'
        prefix_sum.full_name = '누적합'
        prefix_sum.save(update_fields=('name', 'full_name'))


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0040_guide_curriculum_and_english_problem_types'),
    ]

    operations = [
        migrations.RunPython(apply_prefix_sum_and_curriculum, restore_before_prefix_sum),
    ]
