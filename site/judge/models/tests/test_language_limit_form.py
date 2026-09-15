from unittest.mock import patch

from django.contrib import admin
from django.core.validators import MaxValueValidator
from django.forms import inlineformset_factory, modelform_factory
from django.test import RequestFactory, TestCase, override_settings

from judge.admin.problem import LanguageLimitInline, LanguageLimitInlineForm
from judge.models import Language, LanguageLimit, Problem
from judge.models.tests.util import create_problem, create_user


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class LanguageLimitFormTest(TestCase):
    fields = ('language', 'time_limit', 'memory_limit', 'memory_unit')

    def setUp(self):
        self.python, _ = Language.objects.get_or_create(key='PY3', defaults={'name': 'Python 3'})
        self.cpp, _ = Language.objects.get_or_create(key='CPP17', defaults={'name': 'C++17'})
        self.problem = create_problem(code='memory-unit-form')
        self.form_class = modelform_factory(LanguageLimit, form=LanguageLimitInlineForm, fields=self.fields)

    def make_form(self, memory=1024, unit='MB', instance=None, **kwargs):
        return self.form_class(
            data={'language': self.python.pk, 'time_limit': 10, 'memory_limit': memory, 'memory_unit': unit},
            instance=instance or LanguageLimit(problem=self.problem), **kwargs,
        )

    def test_new_form_defaults_to_mb(self):
        form = self.form_class()
        self.assertEqual(form['memory_unit'].value(), 'MB')
        self.assertIsNone(form['memory_limit'].value())

    def test_save_mb_and_kb_to_existing_kb_column(self):
        for unit, expected in (('MB', 1048576), ('KB', 1024)):
            with self.subTest(unit=unit):
                form = self.make_form(unit=unit)
                self.assertTrue(form.is_valid(), form.errors)
                limit = form.save(commit=False)
                self.assertEqual(limit.memory_limit, expected)
                limit.save()
                limit.refresh_from_db()
                self.assertEqual(limit.memory_limit, expected)
                limit.delete()

    def test_existing_values_display_without_precision_loss(self):
        for stored_kb, displayed, unit in ((1048576, 1024, 'MB'), (1024, 1, 'MB'), (1536, 1536, 'KB'), (0, 0, 'KB')):
            with self.subTest(stored_kb=stored_kb):
                limit = LanguageLimit.objects.create(
                    problem=self.problem, language=self.python, time_limit=10, memory_limit=stored_kb,
                )
                form = self.form_class(instance=limit)
                self.assertEqual(form['memory_limit'].value(), displayed)
                self.assertEqual(form['memory_unit'].value(), unit)
                self.assertEqual(limit.memory_limit, stored_kb)
                posted = self.make_form(memory=displayed, unit=unit, instance=limit)
                self.assertFalse(posted.has_changed())
                self.assertTrue(posted.is_valid(), posted.errors)
                posted.save()
                limit.refresh_from_db()
                self.assertEqual(limit.memory_limit, stored_kb)
                limit.delete()

    def test_existing_one_mb_can_be_changed_to_1024_mb(self):
        limit = LanguageLimit.objects.create(
            problem=self.problem, language=self.python, time_limit=10, memory_limit=1024,
        )
        form = self.make_form(instance=limit)
        self.assertTrue(form.has_changed())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.is_valid())  # Validation must not apply the conversion twice.
        form.save()
        limit.refresh_from_db()
        self.assertEqual(limit.memory_limit, 1048576)

    def test_model_validators_receive_converted_kb(self):
        # Verify the limit against stored KB, not the smaller number entered in MB.
        validator = next(v for v in LanguageLimit._meta.get_field('memory_limit').validators
                         if isinstance(v, MaxValueValidator))
        with patch.object(validator, 'limit_value', 1048576):
            valid = self.make_form(memory=1024)
            self.assertTrue(valid.is_valid(), valid.errors)
            invalid = self.make_form(memory=1025)
            self.assertFalse(invalid.is_valid())
            self.assertIn('memory_limit', invalid.errors)
            self.assertEqual(invalid['memory_limit'].value(), 1025)
            self.assertEqual(invalid['memory_unit'].value(), 'MB')

    def test_invalid_input_is_rejected_without_saving(self):
        for memory, unit in ((-1, 'MB'), ('1.5', 'MB'), ('', 'MB'), (1024, 'GB'), (1024, '')):
            with self.subTest(memory=memory, unit=unit):
                form = self.make_form(memory=memory, unit=unit)
                self.assertFalse(form.is_valid())
        self.assertFalse(self.problem.language_limits.exists())

    def test_admin_inline_contains_unit_selector(self):
        request = RequestFactory().get('/admin/judge/problem/%s/change/' % self.problem.pk)
        request.user = create_user(username='memory-unit-admin', is_staff=True, is_superuser=True)
        inline = LanguageLimitInline(Problem, admin.site)
        formset = inline.get_formset(request, self.problem)(instance=self.problem)
        html = str(formset.empty_form['memory_unit'])
        self.assertIn('<select', html)
        self.assertIn('value="KB"', html)
        self.assertIn('value="MB" selected', html)

    def test_inline_rows_use_independent_units(self):
        formset_class = inlineformset_factory(
            Problem, LanguageLimit, form=LanguageLimitInlineForm, fields=self.fields, extra=0,
        )
        data = {'limits-TOTAL_FORMS': '2', 'limits-INITIAL_FORMS': '0'}
        for index, language, memory, unit in ((0, self.python, 1024, 'MB'), (1, self.cpp, 1536, 'KB')):
            data.update({
                'limits-%d-language' % index: str(language.pk),
                'limits-%d-time_limit' % index: '10',
                'limits-%d-memory_limit' % index: str(memory),
                'limits-%d-memory_unit' % index: unit,
            })
        formset = formset_class(data, instance=self.problem, prefix='limits')
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(self.problem.language_limits.get(language=self.python).memory_limit, 1048576)
        self.assertEqual(self.problem.language_limits.get(language=self.cpp).memory_limit, 1536)
