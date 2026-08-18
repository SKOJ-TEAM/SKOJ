from django.test import SimpleTestCase, override_settings

from judge.utils.runtime_paths import judge_debug_log_path, problem_data_path


class RuntimePathTest(SimpleTestCase):
    @override_settings(DMOJ_PROBLEM_DATA_ROOT='/problems')
    def test_problem_data_path_uses_configured_root(self):
        self.assertEqual(problem_data_path('hello', 'data.zip'), '/problems/hello/data.zip')

    @override_settings(BASE_DIR='/app/site')
    def test_debug_log_path_uses_project_dummy_directory(self):
        self.assertEqual(judge_debug_log_path(), '/app/site/dummy/log.ksl')

    @override_settings(DMOJ_PROBLEM_DATA_ROOT='/problems', BASE_DIR='/app/site')
    def test_paths_do_not_embed_macos_home(self):
        paths = [problem_data_path('a'), judge_debug_log_path()]
        self.assertTrue(all('/Users/' not in path for path in paths))
