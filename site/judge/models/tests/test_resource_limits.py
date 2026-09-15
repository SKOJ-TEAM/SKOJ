from unittest.mock import patch

from django.core.cache import cache
from django.forms import modelform_factory
from django.test import TestCase, override_settings

from judge.admin.problem import LanguageLimitInlineForm
from judge.bridge.judge_handler import JudgeHandler
from judge.models import Language, LanguageLimit, Submission
from judge.models.tests.util import create_problem, create_user
from judge.utils.resource_limits import execution_memory_limit
from judge.views.api.api_v2 import APIProblemDetail


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class PythonResourceLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.python, _ = Language.objects.update_or_create(
            key='PY3', defaults={'name': 'Python 3', 'common_name': 'Python'},
        )
        self.cpp, _ = Language.objects.update_or_create(
            key='CPP17', defaults={'name': 'C++17', 'common_name': 'C++'},
        )
        self.problem = create_problem(
            code='python-time-cap', time_limit=15, memory_limit_1=1024, memory_unit='MB',
            allowed_languages=('PY3', 'CPP17'),
        )
        self.submission = Submission.objects.create(
            user=create_user(username='time-limit-user').profile,
            problem=self.problem, language=self.python,
        )

    def bridge_limits(self):
        # Resolve the actual submission payload without starting a judge or rejudging.
        # The daemon connection check would close TestCase's atomic connection.
        with patch('judge.bridge.judge_handler._ensure_connection'):
            return JudgeHandler.get_related_submission_data(None, self.submission.pk)

    def api_limits(self):
        data = APIProblemDetail().get_object_data(self.problem)
        return {limit['language']: limit for limit in data['language_resource_limits']}

    def test_python_without_override_uses_problem_limit_capped_at_ten(self):
        for configured, expected in ((0.5, 0.5), (2, 2), (10, 10), (15, 10)):
            with self.subTest(configured=configured):
                self.problem.time_limit = configured
                self.problem.save()
                result = self.bridge_limits()
                self.assertEqual(result.time, expected)
                self.assertEqual(result.memory, 1048576)

    def test_python_override_takes_precedence_then_is_capped(self):
        limit = LanguageLimit.objects.create(
            problem=self.problem, language=self.python, time_limit=2, memory_limit=1024,
        )
        for configured, expected in ((2, 2), (10, 10), (15, 10)):
            with self.subTest(configured=configured):
                limit.time_limit = configured
                limit.save()
                result = self.bridge_limits()
                self.assertEqual(result.time, expected)
                self.assertEqual(result.memory, 1024)
                self.assertIn(('Python 3', expected), self.problem.language_time_limit)
                self.assertEqual(self.api_limits()['PY3']['time_limit'], expected)
                self.assertEqual(self.api_limits()['PY3']['memory_limit'], 1024)

    def test_implicit_python_cap_is_shown_in_page_and_api(self):
        self.assertIn(('Python 3', 10), self.problem.language_time_limit)
        self.assertEqual(self.api_limits()['PY3'], {
            'language': 'PY3', 'time_limit': 10, 'memory_limit': 1048576,
        })
        self.assertFalse(self.problem.language_limits.exists())

    def test_python_override_above_problem_default_uses_its_own_cap(self):
        self.problem.time_limit = 2
        self.problem.save()
        limit = LanguageLimit.objects.create(
            problem=self.problem, language=self.python, time_limit=15, memory_limit=1048576,
        )
        self.assertEqual(self.bridge_limits().time, 10)
        self.assertIn(('Python 3', 10), self.problem.language_time_limit)
        self.assertEqual(self.api_limits()['PY3']['time_limit'], 10)
        limit.refresh_from_db()
        self.assertEqual(limit.time_limit, 15)

    def test_shared_python_display_name_does_not_hide_different_limits(self):
        python2, _ = Language.objects.update_or_create(
            key='PY2', defaults={'name': 'Python 2', 'common_name': 'Python'},
        )
        for language in (python2, self.python):
            LanguageLimit.objects.create(
                problem=self.problem, language=language, time_limit=100, memory_limit=262144,
            )
        self.assertCountEqual(self.problem.language_time_limit, [('Python 2', 100), ('Python 3', 10)])

    def test_old_display_cache_does_not_override_effective_limit(self):
        cache.set('problem_tls:%d' % self.problem.pk, [('Python 3', 15)])
        self.assertEqual(self.problem.language_time_limit, [('Python 3', 10)])

    def test_other_languages_keep_default_and_override_times(self):
        self.submission.language = self.cpp
        self.submission.save()
        self.assertEqual(self.bridge_limits().time, 15)
        self.assertEqual(self.bridge_limits().memory, 1048576)
        LanguageLimit.objects.create(
            problem=self.problem, language=self.cpp, time_limit=25, memory_limit=262144,
        )
        self.assertEqual(self.bridge_limits().time, 25)
        self.assertEqual(self.bridge_limits().memory, 262144)
        self.assertIn(('C++17', 25), self.problem.language_time_limit)
        self.assertEqual(self.api_limits()['CPP17']['time_limit'], 25)
        self.assertEqual(self.api_limits()['CPP17']['memory_limit'], 262144)
        self.assertIn(('C++17', 262144), self.problem.language_memory_limit)

    def test_python_memory_override_takes_precedence_then_is_capped(self):
        limit = LanguageLimit.objects.create(
            problem=self.problem, language=self.python, time_limit=10, memory_limit=1024,
        )
        for problem_mb, override_kb, expected_kb in (
            (1024, 1024, 1024),  # Submission 772 keeps its smaller 1 MiB allowance.
            (256, 128 * 1024, 128 * 1024),
            (256, 512 * 1024, 512 * 1024),
            (256, 1024 * 1024, 1024 * 1024),
            (256, 2048 * 1024, 1024 * 1024),
            (2048, 3072 * 1024, 1024 * 1024),
            (2048, 512 * 1024, 512 * 1024),
            (256, 0, 1024 * 1024),
            (0, 128 * 1024, 128 * 1024),
        ):
            with self.subTest(problem_mb=problem_mb, override_kb=override_kb):
                self.problem.memory_limit_1 = problem_mb
                self.problem.save()
                limit.memory_limit = override_kb
                limit.save()
                self.assertEqual(self.bridge_limits().memory, expected_kb)
                self.assertEqual(self.api_limits()['PY3']['memory_limit'], expected_kb)
                displayed = dict(self.problem.language_memory_limit)
                self.assertEqual(displayed.get('Python 3', self.problem.memory_limit), expected_kb)
                limit.refresh_from_db()
                self.assertEqual(limit.memory_limit, override_kb)

    def test_memory_cap_without_override_is_shown_even_with_short_time(self):
        self.problem.time_limit = 2
        for problem_mb, expected_mb in ((256, 256), (1024, 1024), (2048, 1024), (0, 1024)):
            with self.subTest(problem_mb=problem_mb):
                self.problem.memory_limit_1 = problem_mb
                self.problem.save()
                expected_kb = expected_mb * 1024
                self.assertEqual(self.bridge_limits().memory, expected_kb)
                displayed = dict(self.problem.language_memory_limit)
                self.assertEqual(displayed.get('Python 3', self.problem.memory_limit), expected_kb)
                api = self.api_limits().get('PY3', {'memory_limit': self.problem.memory_limit})
                self.assertEqual(api['memory_limit'], expected_kb)
                self.assertFalse(self.problem.language_limits.exists())

    def test_old_memory_display_cache_does_not_hide_smaller_override(self):
        LanguageLimit.objects.create(
            problem=self.problem, language=self.python, time_limit=10, memory_limit=1024,
        )
        cache.set('problem_mls:%d' % self.problem.pk, [('Python 3', 1048576)])
        self.assertEqual(self.problem.language_memory_limit, [('Python 3', 1024)])
        self.assertEqual(self.bridge_limits().memory, 1024)

    def test_unset_python_memory_still_has_a_finite_ceiling(self):
        self.assertEqual(execution_memory_limit('PY3', None), 1048576)
        self.assertEqual(execution_memory_limit('PY3', 1024), 1024)

    def test_problem_memory_unit_conversion_does_not_change_language_override(self):
        limit = LanguageLimit.objects.create(
            problem=self.problem, language=self.python, time_limit=10, memory_limit=1024,
        )
        for unit, expected_kb in (('MB', 1048576), ('KB', 1024), ('MB', 1048576)):
            with self.subTest(unit=unit):
                self.problem.memory_limit_1 = 1024
                self.problem.memory_unit = unit
                self.problem.save()
                self.problem.refresh_from_db()
                limit.refresh_from_db()
                self.assertEqual(self.problem.memory_limit, expected_kb)
                self.assertEqual(limit.memory_limit, 1024)
                self.assertEqual(self.bridge_limits().memory, 1024)

    def test_language_memory_form_offers_kb_and_mb(self):
        form_class = modelform_factory(
            LanguageLimit, form=LanguageLimitInlineForm,
            fields=('language', 'time_limit', 'memory_limit', 'memory_unit'),
        )
        self.assertEqual(list(form_class.base_fields['memory_unit'].choices), [('KB', 'KB'), ('MB', 'MB')])

    def test_no_extra_python_row_when_default_is_at_or_below_cap(self):
        self.problem.time_limit = 2
        self.problem.save()
        self.assertEqual(self.problem.language_time_limit, [])
        self.assertNotIn('PY3', self.api_limits())

    def test_no_implicit_python_row_when_python_is_not_allowed(self):
        self.problem.allowed_languages.remove(self.python)
        self.assertEqual(self.problem.language_time_limit, [])
        self.assertNotIn('PY3', self.api_limits())
