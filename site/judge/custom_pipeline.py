# judge/custom_pipeline.py
from django.http import HttpResponseRedirect
from django.urls import reverse


def validate_keycloak_user(backend, details, user, *args, **kwargs):
    """등록되지 않았거나 비활성화된 Keycloak 사용자의 로그인 흐름을 중단한다."""
    if user is None:
        request = backend.strategy.request
        request.session.flush()
        return HttpResponseRedirect(reverse('registration_register'))

    if not user.is_active:
        request = backend.strategy.request
        request.session.flush()
        return HttpResponseRedirect(reverse('activation_required'))

    return {}
