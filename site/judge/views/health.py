import os

from django.core.cache import cache
from django.db import connections
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def healthz(_request):
    """자격 증명이나 내부 주소를 노출하지 않고 배포 readiness를 반환합니다."""
    # 각 공유 의존성을 독립적으로 표시해 배포 실패 원인을 구분할 수 있게 합니다.
    checks = {'database': False, 'redis': False}

    try:
        # ORM 모델과 무관한 최소 쿼리로 현재 DB 연결과 응답 가능 여부를 확인합니다.
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT 1')
            checks['database'] = cursor.fetchone() == (1,)
    except Exception:
        # backend 예외와 접속 정보를 배포 출력에 노출하지 않고 통제된 503으로 변환합니다.
        pass

    try:
        # 값을 쓰거나 삭제하지 않는 get으로 Django Redis cache 연결을 확인합니다.
        cache.get('skoj:healthz:probe')
        checks['redis'] = True
    except Exception:
        pass

    # DB와 Redis가 모두 정상일 때만 Nginx 전환 가능한 Web으로 판정합니다.
    ready = all(checks.values())
    return JsonResponse({
        'status': 'ok' if ready else 'unavailable',
        # 배포 스크립트는 이 값이 요청한 Git SHA와 같은지도 함께 검사합니다.
        'release': os.environ.get('RELEASE_ID', 'development'),
        'checks': checks,
    }, status=200 if ready else 503)
