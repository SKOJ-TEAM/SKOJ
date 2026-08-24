from django.contrib import admin
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from judge.admin.guide import AlgorithmGuideAdmin, AlgorithmGuideForm
from judge.models import AlgorithmGuide, ProblemType
from judge.models.tests.util import CommonDataMixin
from judge.widgets import AdminMartorWidget


class AlgorithmGuideModelTest(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.problem_type = ProblemType.objects.create(name='sorting-guide', full_name='정렬')

    def test_string_and_absolute_url(self):
        guide = AlgorithmGuide.objects.create(
            problem_type=self.problem_type,
            title='버블 정렬',
            summary='버블 정렬의 원리를 배웁니다.',
            content='# 버블 정렬',
        )

        self.assertEqual(str(guide), '버블 정렬')
        self.assertEqual(
            guide.get_absolute_url(),
            reverse('guide_detail', args=('sorting-guide', guide.pk)),
        )

    def test_problem_type_with_guides_is_protected(self):
        AlgorithmGuide.objects.create(
            problem_type=self.problem_type,
            title='버블 정렬',
            summary='요약',
            content='본문',
        )

        with self.assertRaises(ProtectedError):
            self.problem_type.delete()


class AlgorithmGuideAdminTest(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.problem_type = ProblemType.objects.create(name='graph-guide', full_name='그래프')

    def test_form_uses_markdown_editor(self):
        form = AlgorithmGuideForm()

        self.assertIsInstance(form.fields['content'].widget, AdminMartorWidget)

    def test_admin_records_creator(self):
        guide_admin = AlgorithmGuideAdmin(AlgorithmGuide, admin.site)
        request = RequestFactory().post('/admin/judge/algorithmguide/add/')
        request.user = self.users['superuser']
        guide = AlgorithmGuide(
            problem_type=self.problem_type,
            title='그래프 탐색',
            summary='요약',
            content='본문',
        )

        guide_admin.save_model(request, guide, form=None, change=False)

        self.assertEqual(guide.created_by, self.users['superuser'])
