"""Optional campus filters for the ranking and user directory."""
from django.http import Http404
from django.urls import reverse
from django.utils.functional import cached_property

from judge.models import Campus


class CampusFilterMixin:
    campus_filter_url_name = None

    @cached_property
    def campus_options(self):
        return list(Campus.objects.order_by('id'))

    @cached_property
    def selected_campus(self):
        code = self.request.GET.get('campus', '')
        if not code:
            return None
        for campus in self.campus_options:
            if campus.code == code:
                return campus
        raise Http404('존재하지 않는 캠퍼스입니다.')

    def filter_campus(self, queryset, profile_path=''):
        if self.selected_campus is None:
            return queryset
        prefix = profile_path + '__' if profile_path else ''
        return queryset.filter(**{prefix + 'training_class__campus': self.selected_campus})

    def get_campus_filter_context(self):
        query = self.request.GET.copy()
        query.pop('page', None)
        query.pop('campus', None)
        path = reverse(self.campus_filter_url_name)
        options = []
        for campus in [None] + self.campus_options:
            params = query.copy()
            if campus is not None:
                params['campus'] = campus.code
            encoded = params.urlencode()
            options.append({
                'name': campus.name if campus is not None else '전체',
                'url': path + ('?' + encoded if encoded else ''),
                'selected': campus == self.selected_campus,
            })
        return {'campus_filters': options, 'selected_campus': self.selected_campus}
