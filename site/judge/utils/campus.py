"""Campus boundaries for user-owned data; shared learning content is unaffected."""


def is_campus_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def profile_campus_id(profile):
    return profile.training_class.campus_id if profile.training_class_id else None


def can_access_profile(user, profile):
    if is_campus_admin(user):
        return True
    if not user.is_authenticated:
        return False
    if user.profile.pk == profile.pk:
        return True
    campus_id = profile_campus_id(user.profile)
    return campus_id is not None and campus_id == profile_campus_id(profile)


def scope_queryset(queryset, user, profile_path='', campus_id=None):
    prefix = profile_path + '__' if profile_path else ''
    campus_lookup = prefix + 'training_class__campus_id'
    if is_campus_admin(user):
        return queryset.filter(**{campus_lookup: campus_id}) if campus_id else queryset
    if not user.is_authenticated:
        return queryset.none()
    campus_id = profile_campus_id(user.profile)
    if campus_id is not None:
        return queryset.filter(**{campus_lookup: campus_id})
    # An unassigned account can see its own records, never everyone else's.
    return queryset.filter(**{prefix + 'pk': user.profile.pk})


def selected_campus(request):
    if is_campus_admin(request.user):
        value = getattr(request, 'session', {}).get('campus_scope')
        if isinstance(value, int) and value > 0:
            return value
    return None


def scope_request(queryset, request, profile_path=''):
    return scope_queryset(queryset, request.user, profile_path, selected_campus(request))
