from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from judge.views.health import healthz


class HealthCheckTestCase(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get('/healthz/')

    @patch('judge.views.health.cache')
    @patch('judge.views.health.connections')
    def test_reports_release_when_database_and_redis_are_ready(self, connections, cache):
        # DB와 Redis가 모두 정상일 때 요청 이미지의 RELEASE_ID와 HTTP 200을 반환해야 합니다.
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        connections.__getitem__.return_value.cursor.return_value.__enter__.return_value = cursor
        cache.get.return_value = None

        with patch.dict('os.environ', {'RELEASE_ID': 'abc123'}):
            response = healthz(self.request)

        self.assertEqual(200, response.status_code)
        self.assertJSONEqual(response.content, {
            'status': 'ok',
            'release': 'abc123',
            'checks': {'database': True, 'redis': True},
        })

    @patch('judge.views.health.cache')
    @patch('judge.views.health.connections')
    def test_returns_503_when_a_dependency_is_unavailable(self, connections, cache):
        # 공유 의존성 하나라도 실패하면 Nginx 전환을 막을 수 있도록 HTTP 503을 반환해야 합니다.
        connections.__getitem__.return_value.cursor.side_effect = RuntimeError('database unavailable')
        cache.get.return_value = None

        response = healthz(self.request)

        self.assertEqual(503, response.status_code)
        self.assertJSONEqual(response.content, {
            'status': 'unavailable',
            'release': 'development',
            'checks': {'database': False, 'redis': True},
        })
