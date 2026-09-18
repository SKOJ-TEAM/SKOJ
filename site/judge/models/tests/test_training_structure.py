from django.contrib.auth.models import AnonymousUser, User
from django.contrib.sites.models import Site
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from judge.models import Campus, Cohort, Contest, Language, TrainingClass
from judge.models.tests.util import CommonDataMixin
from judge.views.register import CustomRegistrationForm
from registration.models import RegistrationProfile


class TrainingStructureModelTest(TestCase):
    def setUp(self):
        self.cohort = Cohort.objects.create(number=3)
        self.pangyo = Campus.objects.create(code='pangyo-test', name='판교 테스트')

    def test_class_is_unique_within_cohort_and_campus(self):
        TrainingClass.objects.create(cohort=self.cohort, campus=self.pangyo, number=1)

        with self.assertRaises(IntegrityError), transaction.atomic():
            TrainingClass.objects.create(cohort=self.cohort, campus=self.pangyo, number=1)

    def test_same_class_number_is_allowed_in_another_cohort_or_campus(self):
        TrainingClass.objects.create(cohort=self.cohort, campus=self.pangyo, number=1)
        other_cohort = Cohort.objects.create(number=4)
        gwangju = Campus.objects.create(code='gwangju-test', name='광주 테스트')

        TrainingClass.objects.create(cohort=other_cohort, campus=self.pangyo, number=1)
        TrainingClass.objects.create(cohort=self.cohort, campus=gwangju, number=1)

        self.assertEqual(TrainingClass.objects.count(), 3)

    def test_class_display_contains_full_affiliation(self):
        training_class = TrainingClass.objects.create(cohort=self.cohort, campus=self.pangyo, number=1)

        self.assertEqual(str(training_class), '3기 판교 테스트 1반')

    def test_zero_cohort_and_class_numbers_are_rejected(self):
        with self.assertRaises(ValidationError):
            Cohort(number=0).full_clean()
        with self.assertRaises(ValidationError):
            TrainingClass(cohort=self.cohort, campus=self.pangyo, number=0).full_clean()


class TrainingRegistrationFormTest(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.cohort = Cohort.objects.create(number=3)
        cls.pangyo = Campus.objects.get(code='pangyo')
        cls.gwangju = Campus.objects.get(code='gwangju')
        cls.training_class = TrainingClass.objects.create(
            cohort=cls.cohort,
            campus=cls.gwangju,
            number=1,
        )
        Site.objects.update_or_create(pk=1, defaults={'domain': 'skoj.site', 'name': 'SKOJ'})

    def form_data(self, **overrides):
        data = {
            'username': 'new_skala_user',
            'first_name': '교육생',
            'email': 'new-skala@example.com',
            'password1': 'N7!qZ4@vL9#sK2',
            'password2': 'N7!qZ4@vL9#sK2',
            'language': Language.objects.first().pk,
            'cohort': self.cohort.pk,
            'campus': self.gwangju.pk,
            'training_class': self.training_class.number,
        }
        data.update(overrides)
        return data

    def test_active_matching_affiliation_is_valid(self):
        form = CustomRegistrationForm(data=self.form_data())

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['training_class'], self.training_class)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='SKOJ <skojteam@gmail.com>',
    )
    def test_registration_creates_inactive_account_and_sends_activation_email(self):
        response = self.client.post(
            reverse('registration_register'),
            self.form_data(),
            secure=True,
        )

        self.assertRedirects(response, reverse('registration_complete'), fetch_redirect_response=False)
        user = User.objects.get(username='new_skala_user')
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.training_class, self.training_class)
        registration_profile = RegistrationProfile.objects.get(user=user)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['new-skala@example.com'])
        self.assertIn(
            f'https://skoj.site/accounts/activate/{registration_profile.activation_key}/',
            mail.outbox[0].body,
        )

    def test_training_class_options_include_filter_metadata(self):
        form = CustomRegistrationForm()
        rendered_campuses = str(form['campus'])
        rendered_classes = str(form['training_class'])

        self.assertIn('data-campus-code="pangyo"', rendered_campuses)
        self.assertIn('value="6"', rendered_classes)
        self.assertIn('캠퍼스를 먼저 선택해 주세요', rendered_classes)
        self.assertNotIn('django-select2', rendered_classes)

    def test_mismatched_campus_is_rejected(self):
        form = CustomRegistrationForm(data=self.form_data(campus=self.pangyo.pk))

        self.assertFalse(form.is_valid())
        self.assertIn('선택한 반을 등록할 수 없습니다. 관리자에게 문의해 주세요.',
                      form.non_field_errors())

    def test_registration_page_does_not_render_non_field_errors_method(self):
        response = self.client.get(reverse('registration_register'), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'bound method BaseForm.non_field_errors')

    def test_registration_page_renders_non_field_errors(self):
        response = self.client.post(
            reverse('registration_register'),
            self.form_data(campus=self.pangyo.pk),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '선택한 반을 등록할 수 없습니다.')
        self.assertNotContains(response, 'bound method BaseForm.non_field_errors')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_pangyo_and_ulsan_classes_allow_registration(self):
        for code, number in (('pangyo', 6), ('ulsan', 4)):
            campus = Campus.objects.get(code=code)
            training_class = TrainingClass.objects.create(cohort=self.cohort, campus=campus, number=number)
            data = self.form_data(campus=campus.pk, training_class=number,
                                  username='new_' + code, email=code + '@example.com')
            form = CustomRegistrationForm(data=data)
            self.assertTrue(form.is_valid(), form.errors)
            response = self.client.post(reverse('registration_register'), data, secure=True)
            self.assertRedirects(response, reverse('registration_complete'), fetch_redirect_response=False)
            user = User.objects.get(username=data['username'])
            self.assertFalse(user.is_active)
            self.assertEqual(user.profile.training_class, training_class)
            self.assertTrue(RegistrationProfile.objects.filter(user=user).exists())
        self.assertEqual(len(mail.outbox), 2)

    def test_inactive_class_is_not_selectable(self):
        self.training_class.is_active = False
        self.training_class.save(update_fields=['is_active'])
        form = CustomRegistrationForm(data=self.form_data())

        self.assertFalse(form.is_valid())
        self.assertIn('선택한 반을 등록할 수 없습니다. 관리자에게 문의해 주세요.',
                      form.non_field_errors())

    def test_gwangju_fifth_class_is_rejected(self):
        form = CustomRegistrationForm(data=self.form_data(training_class=5))

        self.assertFalse(form.is_valid())
        self.assertIn('선택한 캠퍼스에서 운영하지 않는 반입니다.', form.non_field_errors())

    def test_missing_ulsan_class_is_rejected(self):
        ulsan = Campus.objects.get(code='ulsan')
        form = CustomRegistrationForm(data=self.form_data(campus=ulsan.pk, training_class=4))

        self.assertFalse(form.is_valid())
        self.assertIn('선택한 반을 등록할 수 없습니다. 관리자에게 문의해 주세요.',
                      form.non_field_errors())


class ClassRestrictedContestTest(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cohort = Cohort.objects.create(number=3)
        campus = Campus.objects.create(code='pangyo-contest', name='판교 대회')
        cls.allowed_class = TrainingClass.objects.create(cohort=cohort, campus=campus, number=1)
        cls.other_class = TrainingClass.objects.create(cohort=cohort, campus=campus, number=2)
        now = timezone.now()
        cls.contest = Contest(key='class-limited', name='반 제한 대회', is_visible=True,
                              start_time=now - timezone.timedelta(days=1),
                              end_time=now + timezone.timedelta(days=1))
        cls.contest.save()
        cls.contest.allowed_classes.add(cls.allowed_class)

        cls.other_user = cls.users['normal']
        cls.allowed_user = cls.users['staff_problem_edit_own_no_staff']
        cls.allowed_user.profile.training_class = cls.allowed_class
        cls.allowed_user.profile.save(update_fields=['training_class'])
        cls.other_user.profile.training_class = cls.other_class
        cls.other_user.profile.save(update_fields=['training_class'])

    def test_only_allowed_class_sees_contest(self):
        self.assertTrue(self.contest.is_accessible_by(self.allowed_user))
        self.assertFalse(self.contest.is_accessible_by(self.other_user))
        self.assertFalse(self.contest.is_accessible_by(AnonymousUser()))

        self.assertTrue(self.contest in self.contest.get_visible_contests(self.allowed_user))
        self.assertFalse(self.contest in self.contest.get_visible_contests(self.other_user))
