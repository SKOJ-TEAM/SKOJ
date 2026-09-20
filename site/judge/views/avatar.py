from functools import partial

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_POST
from reversion import revisions

from judge.jinja2.gravatar import gravatar
from judge.models import Profile
from judge.utils.avatars import delete_unused_avatar, new_avatar_name, prepare_avatar


class AvatarForm(forms.Form):
    action = forms.ChoiceField(choices=(('upload', 'upload'), ('remove', 'remove')))
    image = forms.FileField(required=False)
    crop_x = forms.FloatField(required=False)
    crop_y = forms.FloatField(required=False)
    crop_size = forms.FloatField(required=False)

    def clean(self):
        data = super().clean()
        if data.get('action') == 'remove':
            if self.files:
                raise ValidationError('사진 삭제와 업로드를 동시에 할 수 없습니다.')
            return data
        if data.get('action') != 'upload' or self.errors:
            return data
        if not data.get('image') or any(data.get(key) is None for key in ('crop_x', 'crop_y', 'crop_size')):
            raise ValidationError('사진을 선택하고 잘라낼 영역을 조절해주세요.')
        if len(self.files.getlist('image')) != 1 or len(self.files) != 1:
            raise ValidationError('사진은 한 장씩 올려주세요.')
        data['processed_image'] = prepare_avatar(data['image'], data['crop_x'], data['crop_y'], data['crop_size'])
        return data


@login_required
@require_POST
def edit_avatar(request):
    if request.profile.mute:
        raise Http404()
    form = AvatarForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
    new_name = ''
    try:
        if form.cleaned_data['action'] == 'upload':
            new_name = default_storage.save(new_avatar_name(), form.cleaned_data['processed_image'])
        with transaction.atomic(), revisions.create_revision():
            profile = Profile.objects.select_for_update().get(user=request.user)
            if profile.mute:
                raise Http404()
            old_name = profile.avatar.name
            profile.avatar = new_name
            profile.save(update_fields=['avatar'])
            revisions.set_user(request.user)
            revisions.set_comment('Updated profile photo on site')
            if old_name:
                transaction.on_commit(partial(delete_unused_avatar, old_name))
    except Exception:
        if new_name:
            delete_unused_avatar(new_name)
        raise
    return JsonResponse({'avatar_url': gravatar(profile, 135), 'has_avatar': bool(profile.avatar)})
