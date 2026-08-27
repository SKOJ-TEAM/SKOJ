from contextlib import nullcontext
import smtplib
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from judge.views.register import (
    CustomRegistrationForm,
    RegistrationView,
    _validate_registration_username,
)


class RegistrationFieldsTestCase(SimpleTestCase):
    def test_registration_form_has_only_requested_profile_fields(self):
        fields = CustomRegistrationForm.base_fields

        self.assertIn('username', fields)
        self.assertIn('password1', fields)
        self.assertIn('password2', fields)
        self.assertIn('first_name', fields)
        self.assertIn('email', fields)
        self.assertIn('language', fields)
        self.assertIn('cohort', fields)
        self.assertIn('campus', fields)
        self.assertIn('training_class', fields)
        self.assertNotIn('email_local', fields)
        self.assertNotIn('email_domain', fields)

    def test_username_accepts_normal_identifier(self):
        self.assertEqual(_validate_registration_username('skoj_user1'), [])

    def test_username_rejects_spaces_and_special_characters(self):
        errors = _validate_registration_username('skoj user!')

        self.assertEqual(errors, ['아이디는 영문자, 숫자, 밑줄(_)만 사용할 수 있습니다.'])

    @patch('judge.views.register.transaction.atomic', return_value=nullcontext())
    @patch('judge.views.register.get_current_site', return_value=Mock())
    @patch('judge.views.register.RegistrationProfile.objects.create_profile')
    @patch('judge.views.register.signals.user_registered.send')
    @patch('judge.views.register.Profile.objects.get_or_create')
    @patch('judge.views.register.Language.get_default_language', return_value='PY3')
    def test_registration_creates_inactive_user_and_sends_activation_email(
            self, get_default_language, get_or_create, send_signal, create_registration_profile,
            get_current_site, atomic):
        user = Mock(is_active=True, first_name='')
        profile = SimpleNamespace(timezone=None, language=None, training_class=None, save=Mock())
        registration_profile = Mock()
        get_or_create.return_value = (profile, True)
        create_registration_profile.return_value = registration_profile
        form = Mock()
        form.save.return_value = user
        form.cleaned_data = {
            'first_name': '테스트',
            'language': 'PY3',
            'training_class': '3기 판교 1반',
        }
        view = RegistrationView()
        view.request = Mock(session={})

        result = view.register(form)

        self.assertIs(result, user)
        self.assertFalse(user.is_active)
        form.save.assert_called_once_with(commit=False)
        user.save.assert_called_once_with()
        create_registration_profile.assert_called_once_with(user)
        registration_profile.send_activation_email.assert_called_once_with(
            site=get_current_site.return_value,
            request=view.request,
        )
        self.assertTrue(view.request.session['registration_email_sent'])
        send_signal.assert_called_once_with(
            sender=RegistrationView,
            user=user,
            request=view.request,
        )

    @patch('judge.views.register.logger.exception')
    @patch('judge.views.register.transaction.atomic', return_value=nullcontext())
    @patch('judge.views.register.get_current_site', return_value=Mock())
    @patch('judge.views.register.RegistrationProfile.objects.create_profile')
    @patch('judge.views.register.signals.user_registered.send')
    @patch('judge.views.register.Profile.objects.get_or_create')
    @patch('judge.views.register.Language.get_default_language', return_value='PY3')
    def test_registration_preserves_inactive_user_when_email_delivery_fails(
            self, get_default_language, get_or_create, send_signal, create_registration_profile,
            get_current_site, atomic, logger_exception):
        user = Mock(is_active=True, first_name='')
        profile = SimpleNamespace(timezone=None, language=None, training_class=None, save=Mock())
        registration_profile = Mock()
        registration_profile.send_activation_email.side_effect = smtplib.SMTPException('unavailable')
        get_or_create.return_value = (profile, True)
        create_registration_profile.return_value = registration_profile
        form = Mock()
        form.save.return_value = user
        form.cleaned_data = {
            'first_name': '테스트',
            'language': 'PY3',
            'training_class': '3기 판교 1반',
        }
        view = RegistrationView()
        view.request = Mock(session={})

        result = view.register(form)

        self.assertIs(result, user)
        self.assertFalse(user.is_active)
        user.save.assert_called_once_with()
        self.assertFalse(view.request.session['registration_email_sent'])
