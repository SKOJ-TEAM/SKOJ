from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from judge.admin.problem import ProblemAdmin
from judge.admin.taxon import ProblemGroupAdmin, ProblemGroupForm
from judge.models import Problem, ProblemGroup
from judge.models.tests.util import create_problem, create_problem_group


@override_settings(SECURE_SSL_REDIRECT=False)
class ProblemGroupAdminOrderTestCase(TestCase):
    def setUp(self):
        self.group = create_problem_group(name='admin-order', full_name='관리 순서')
        self.other_group = create_problem_group(name='admin-order-other', full_name='다른 그룹')
        self.first = create_problem(
            code='adminorder001', name='첫 문제', group=self.group, group_order=2,
        )
        self.second = create_problem(
            code='adminorder002', name='둘째 문제', group=self.group, group_order=1,
        )
        self.new_problem = create_problem(
            code='adminorder003', name='새 문제', group=self.other_group,
        )

    def test_form_initializes_with_saved_group_order(self):
        form = ProblemGroupForm(instance=self.group)

        self.assertEqual(form.fields['problem_order'].initial, '%s,%s' % (self.second.pk, self.first.pk))
        self.assertEqual(
            form.fields['problem_order'].widget.attrs['data-original-problem-ids'],
            '%s,%s' % (self.second.pk, self.first.pk),
        )

    def test_admin_change_page_loads_order_controls_and_assets(self):
        user = get_user_model().objects.create_superuser(
            username='problem-group-admin',
            email='admin@example.com',
            password='test-password',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('admin:judge_problemgroup_change', args=(self.group.pk,)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'admin/js/problem_group_order.js')
        self.assertContains(response, 'admin/css/problem_group_order.css')
        self.assertContains(response, 'data-original-problem-ids="%s,%s"' % (
            self.second.pk, self.first.pk,
        ))

    def test_form_rejects_duplicate_and_removed_existing_problems(self):
        duplicate_form = ProblemGroupForm(data={
            'name': self.group.name,
            'full_name': self.group.full_name,
            'problems': [self.first.pk, self.second.pk],
            'problem_order': '%s,%s,%s' % (self.first.pk, self.first.pk, self.second.pk),
        }, instance=self.group)
        removed_form = ProblemGroupForm(data={
            'name': self.group.name,
            'full_name': self.group.full_name,
            'problems': [self.first.pk],
            'problem_order': str(self.first.pk),
        }, instance=self.group)

        self.assertFalse(duplicate_form.is_valid())
        self.assertIn('problem_order', duplicate_form.errors)
        self.assertFalse(removed_form.is_valid())
        self.assertIn('problems', removed_form.errors)

    def test_save_reorders_existing_and_moves_new_problem_atomically(self):
        form = ProblemGroupForm(data={
            'name': self.group.name,
            'full_name': self.group.full_name,
            'problems': [self.first.pk, self.second.pk, self.new_problem.pk],
            'problem_order': '%s,%s,%s' % (self.new_problem.pk, self.first.pk, self.second.pk),
        }, instance=self.group)
        self.assertTrue(form.is_valid(), form.errors)

        model_admin = ProblemGroupAdmin(ProblemGroup, admin.site)
        model_admin.save_model(RequestFactory().post('/admin/'), self.group, form, change=True)

        ordered = list(
            self.group.problem_set.order_by('group_order').values_list('pk', 'group_order')
        )
        self.assertEqual(ordered, [
            (self.new_problem.pk, 1),
            (self.first.pk, 2),
            (self.second.pk, 3),
        ])

    def test_new_selection_is_appended_without_javascript(self):
        form = ProblemGroupForm(data={
            'name': self.group.name,
            'full_name': self.group.full_name,
            'problems': [self.first.pk, self.second.pk, self.new_problem.pk],
            'problem_order': '%s,%s' % (self.second.pk, self.first.pk),
        }, instance=self.group)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['problem_order'],
            [self.second.pk, self.first.pk, self.new_problem.pk],
        )

    def test_problem_admin_group_change_resets_saved_order(self):
        self.first.group = self.other_group
        self.first.group_order = 9

        class FormStub:
            cleaned_data = {'memory_limit_1': 64, 'memory_unit': 'MB'}
            changed_data = ['group']

        ProblemAdmin(Problem, admin.site).save_model(
            RequestFactory().post('/admin/'), self.first, FormStub(), change=True,
        )

        self.first.refresh_from_db()
        self.assertEqual(self.first.group, self.other_group)
        self.assertIsNone(self.first.group_order)
