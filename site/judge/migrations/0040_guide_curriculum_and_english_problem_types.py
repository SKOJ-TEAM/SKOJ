from django.db import migrations


# (legacy name, canonical slug, English display name, curriculum order, legacy guide order)
GUIDE_CURRICULUM = (
    ('시간복잡도', 'time-complexity', 'Time Complexity', 1, 21),
    ('연결리스트', 'array-linked-list', 'Arrays and Linked Lists', 2, 0),
    ('재귀', 'recursion', 'Recursion', 3, 18),
    ('스택', 'stack', 'Stack', 4, 20),
    ('큐', 'queue', 'Queue', 5, 17),
    ('덱', 'deque', 'Deque', 6, 6),
    ('해시', 'hash', 'Hash Tables', 7, 13),
    ('브루트포스', 'brute-force', 'Brute Force', 8, 5),
    ('백트래킹', 'backtracking', 'Backtracking', 9, 1),
    ('정렬', 'sorting', 'Sorting', 10, 19),
    ('이분탐색', 'binary-search', 'Binary Search', 11, 3),
    ('트리', 'tree', 'Tree', 12, 23),
    ('이진 검색 트리', 'binary-search-tree', 'Binary Search Tree', 13, 4),
    ('힙', 'heap', 'Heap', 14, 14),
    ('트라이', 'trie', 'Trie', 15, 24),
    ('그래프', 'graph', 'Graph', 16, 11),
    ('DFS', 'dfs', 'Depth-First Search (DFS)', 17, 7),
    ('BFS', 'bfs', 'Breadth-First Search (BFS)', 18, 2),
    ('위상정렬', 'topological-sort', 'Topological Sort', 19, 22),
    ('유니온 파인드', 'union-find', 'Union-Find', 20, 25),
    ('그리디', 'greedy', 'Greedy Algorithms', 21, 12),
    ('크루스칼', 'kruskal', "Kruskal's Algorithm", 22, 16),
    ('다익스트라', 'dijkstra', "Dijkstra's Algorithm", 23, 8),
    ('다이나믹 프로그래밍', 'dynamic-programming', 'Dynamic Programming', 24, 9),
    ('플로이드', 'floyd', 'Floyd-Warshall Algorithm', 25, 10),
    ('KMP', 'kmp', 'Knuth-Morris-Pratt (KMP)', 26, 15),
)


def apply_english_problem_types_and_curriculum(apps, schema_editor):
    ProblemType = apps.get_model('judge', 'ProblemType')
    AlgorithmGuide = apps.get_model('judge', 'AlgorithmGuide')

    for legacy_name, slug, full_name, order, _legacy_order in GUIDE_CURRICULUM:
        problem_type = ProblemType.objects.filter(name=legacy_name).first()
        if problem_type is None:
            problem_type = ProblemType.objects.filter(name=slug).first()
        if problem_type is None:
            continue

        problem_type.name = slug
        problem_type.full_name = full_name
        problem_type.save(update_fields=('name', 'full_name'))
        AlgorithmGuide.objects.filter(problem_type_id=problem_type.pk).update(order=order)


def restore_legacy_problem_types_and_order(apps, schema_editor):
    ProblemType = apps.get_model('judge', 'ProblemType')
    AlgorithmGuide = apps.get_model('judge', 'AlgorithmGuide')

    for legacy_name, slug, _full_name, _order, legacy_order in GUIDE_CURRICULUM:
        problem_type = ProblemType.objects.filter(name=slug).first()
        if problem_type is None:
            continue

        problem_type.name = legacy_name
        problem_type.full_name = legacy_name
        problem_type.save(update_fields=('name', 'full_name'))
        AlgorithmGuide.objects.filter(problem_type_id=problem_type.pk).update(order=legacy_order)


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0039_cleanup_legacy_school_metadata'),
    ]

    operations = [
        migrations.RunPython(
            apply_english_problem_types_and_curriculum,
            restore_legacy_problem_types_and_order,
        ),
    ]
