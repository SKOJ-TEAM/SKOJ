from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from judge.models import Campus, Profile
from judge.utils.campus import is_campus_admin, scope_request


@require_POST
def select_campus(request):
    if not is_campus_admin(request.user):
        raise PermissionDenied()
    value = request.POST.get('campus', '')
    if value:
        if len(value) > 10 or not value.isdigit() or not Campus.objects.filter(pk=int(value)).exists():
            return HttpResponseBadRequest('잘못된 캠퍼스입니다.')
        request.session['campus_scope'] = int(value)
    else:
        request.session.pop('campus_scope', None)
    target = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        target = reverse('user_list')
    return HttpResponseRedirect(target)


@login_required
def markdown_search_user(request):
    username = request.GET.get('username', '')
    if not username or ' ' in username:
        return JsonResponse({'status': 204, 'error': '사용자 이름을 입력해 주세요.'})
    names = list(scope_request(Profile.objects.all(), request).filter(
        user__is_active=True, user__username__icontains=username,
    ).values_list('user__username', flat=True)[:20])
    if not names:
        return JsonResponse({'status': 204, 'error': '사용자를 찾을 수 없습니다.'})
    return JsonResponse({'status': 200, 'data': [{'username': name} for name in names]})
