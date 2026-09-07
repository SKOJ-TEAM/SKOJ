from django import forms
from django.contrib import admin
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from judge.models import Problem, ProblemGroup
from judge.widgets import AdminHeavySelect2MultipleWidget


class ProblemMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, problem):
        return '%s — %s' % (problem.code, problem.name)


class ProblemGroupForm(forms.ModelForm):
    problems = ProblemMultipleChoiceField(
        label=_('포함 문제'),
        queryset=Problem.objects.order_by('code'),
        required=False,
        help_text=_('기존 문제는 아래에서 순서를 바꾸고, 다른 그룹의 문제를 선택하면 이 그룹으로 이동합니다.'),
        widget=AdminHeavySelect2MultipleWidget(
            data_view='problem_select2',
            attrs={'style': 'width: 100%'},
        ),
    )
    problem_order = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = ProblemGroup
        fields = ('name', 'full_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_ids = []
        if self.instance and self.instance.pk:
            current_ids = list(
                self.instance.problem_set.order_by_group_order().values_list('pk', flat=True)
            )

        self.current_problem_ids = current_ids
        self.fields['problem_order'].widget.attrs['data-original-problem-ids'] = ','.join(map(str, current_ids))
        if not self.is_bound:
            self.fields['problems'].initial = current_ids
            self.fields['problem_order'].initial = ','.join(map(str, current_ids))

    def clean_problem_order(self):
        raw_order = self.cleaned_data.get('problem_order', '')
        if not raw_order.strip():
            return []

        values = [value.strip() for value in raw_order.split(',')]
        if any(not value.isdigit() for value in values):
            raise forms.ValidationError(_('문제 순서 값이 올바르지 않습니다.'))

        problem_ids = [int(value) for value in values]
        if len(problem_ids) != len(set(problem_ids)):
            raise forms.ValidationError(_('문제 순서에 중복된 문제가 있습니다.'))
        return problem_ids

    def clean(self):
        cleaned_data = super().clean()
        problems = cleaned_data.get('problems')
        problem_order = cleaned_data.get('problem_order')
        if problems is None or problem_order is None:
            return cleaned_data

        selected_ids = set(problems.values_list('pk', flat=True))
        ordered_ids = set(problem_order)
        current_ids = set(self.current_problem_ids)

        if not ordered_ids.issubset(selected_ids):
            self.add_error('problem_order', _('선택하지 않은 문제가 순서에 포함되어 있습니다.'))
            return cleaned_data
        if not current_ids.issubset(ordered_ids):
            self.add_error(
                'problems',
                _('기존 문제는 그룹에서 바로 제거할 수 없습니다. 다른 그룹으로 이동해 주세요.'),
            )
            return cleaned_data

        # JavaScript가 비활성화된 경우에도 새로 선택한 문제는 끝에 추가한다.
        missing_ids = selected_ids - ordered_ids
        if missing_ids:
            problem_order.extend(
                problems.filter(pk__in=missing_ids).order_by('code', 'id').values_list('pk', flat=True)
            )
        cleaned_data['problem_order'] = problem_order
        return cleaned_data

class CustomActionForm(forms.Form):
    action = forms.ChoiceField(
        label="작업",   
        choices=[],           
        required=False,
    )
    select_across = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),   
        label=''
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['action'].choices.insert(0, ("", "작업을 선택하세요."))


class ProblemGroupAdmin(admin.ModelAdmin):
    fields = ('name', 'full_name', 'problems', 'problem_order')
    form = ProblemGroupForm
    action_form = CustomActionForm

    class Media:
        css = {'all': ('admin/css/problem_group_order.css',)}
        # 순서 UI는 django.jQuery를 사용하므로 Django admin 초기화 스크립트를 먼저 불러온다.
        js = ('admin/js/jquery.init.js', 'admin/js/problem_group_order.js')

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            ordered_ids = form.cleaned_data['problem_order']
            problems = Problem.objects.select_for_update().in_bulk(ordered_ids)
            ordered_problems = []
            for position, problem_id in enumerate(ordered_ids, start=1):
                problem = problems[problem_id]
                problem.group_id = obj.pk
                problem.group_order = position
                ordered_problems.append(problem)
            if ordered_problems:
                Problem.objects.bulk_update(ordered_problems, ('group', 'group_order'))
