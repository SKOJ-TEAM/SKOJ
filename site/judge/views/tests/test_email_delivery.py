import smtplib
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser, User
from django.core import mail
from django.test import RequestFactory, SimpleTestCase, override_settings
from registration.models import RegistrationProfile

from judge.views.register import RegistrationCompleteView
from judge.views.user import CustomPasswordResetView, IdFindView, ResendActivationEmailView, _email_rate_limited


MAIL_SETTINGS = {
    'EMAIL_BACKEND': 'django.core.mail.backends.locmem.EmailBackend',
    'DEFAULT_FROM_EMAIL': 'SKOJ <skojteam@gmail.com>',
    'SITE_NAME': 'SKOJ',
    'SITE_ADMIN_EMAIL': 'skojteam@gmail.com',
    'ACCOUNT_ACTIVATION_DAYS': 7,
    'DMOJ_EMAIL_RATE_LIMIT_WINDOW': 3600,
    'DMOJ_EMAIL_RATE_LIMIT_COUNT': 2,
    'CACHES': {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'email-delivery-tests',
        },
    },
}


@override_settings(**MAIL_SETTINGS)
class EmailDeliveryTestCase(SimpleTestCase):
    def setUp(self):
        mail.outbox = []

    def test_activation_email_uses_skoj_sender_and_https_link(self):
        user = User(username='new-user', email='new-user@example.com')
        profile = RegistrationProfile(user=user, activation_key='activation-key')
        request = RequestFactory().get('/', secure=True)
        request.user = AnonymousUser()
        request.LANGUAGE_CODE = 'ko'
        site = SimpleNamespace(domain='skoj.site', name='SKOJ')

        with patch('judge.template_context.get_current_site', return_value=site):
            profile.send_activation_email(site=site, request=request)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.from_email, 'SKOJ <skojteam@gmail.com>')
        self.assertEqual(message.to, ['new-user@example.com'])
        self.assertIn('https://skoj.site/accounts/activate/activation-key/', message.body)

    def test_recipient_rate_limit_blocks_requests_after_configured_count(self):
        self.assertFalse(_email_rate_limited('resend-test', 'User@Example.com'))
        self.assertFalse(_email_rate_limited('resend-test', 'user@example.com'))
        self.assertTrue(_email_rate_limited('resend-test', 'user@example.com'))

    def test_password_reset_links_are_forced_to_https(self):
        self.assertTrue(CustomPasswordResetView.use_https)

    @patch('judge.views.user.Profile.objects.get')
    @patch('judge.views.user.send_mail')
    def test_id_find_uses_configured_sender(self, send_mail, get_profile):
        get_profile.return_value = SimpleNamespace(user=SimpleNamespace(username='skoj-user'))
        form = Mock(cleaned_data={'email': 'member@example.com'})
        view = IdFindView()
        view.request = RequestFactory().post('/accounts/id/find/')
        view.form_invalid = Mock()

        with patch('judge.views.user._email_rate_limited', return_value=False), \
                patch.object(IdFindView.__mro__[1], 'form_valid', return_value='success'):
            response = view.form_valid(form)

        self.assertEqual(response, 'success')
        send_mail.assert_called_once_with(
            subject='SKOJ 아이디 찾기',
            message='아이디: skoj-user',
            from_email='SKOJ <skojteam@gmail.com>',
            recipient_list=['member@example.com'],
            fail_silently=False,
        )

    @patch('judge.views.user.Profile.objects.get')
    @patch('judge.views.user.send_mail', side_effect=smtplib.SMTPException('unavailable'))
    def test_id_find_shows_generic_error_when_delivery_fails(self, send_mail, get_profile):
        get_profile.return_value = SimpleNamespace(user=SimpleNamespace(username='skoj-user'))
        form = Mock(cleaned_data={'email': 'member@example.com'})
        view = IdFindView()
        view.request = RequestFactory().post('/accounts/id/find/')
        view.form_invalid = Mock(return_value='invalid')

        with patch('judge.views.user._email_rate_limited', return_value=False), \
                patch('judge.views.user.logger.exception'):
            response = view.form_valid(form)

        self.assertEqual(response, 'invalid')
        form.add_error.assert_called_once_with(None, '메일을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.')

    @patch('judge.views.user.get_current_site', return_value=SimpleNamespace(domain='skoj.site'))
    @patch('judge.views.user.RegistrationProfile.objects.get_or_create')
    @patch('judge.views.user.User.objects.get')
    def test_activation_resend_refreshes_key_and_sends_email(self, get_user, get_or_create, get_site):
        user = SimpleNamespace(pk=7)
        registration_profile = Mock()
        get_user.return_value = user
        get_or_create.return_value = (registration_profile, False)
        form = Mock(cleaned_data={'username': 'inactive-user'})
        view = ResendActivationEmailView()
        view.request = RequestFactory().post('/accounts/activationmail/resend/')

        with patch('judge.views.user._email_rate_limited', return_value=False), \
                patch.object(ResendActivationEmailView.__mro__[1], 'form_valid', return_value='success'):
            response = view.form_valid(form)

        self.assertEqual(response, 'success')
        registration_profile.create_new_activation_key.assert_called_once_with(save=True)
        registration_profile.send_activation_email.assert_called_once_with(
            site=get_site.return_value,
            request=view.request,
        )

    def test_registration_complete_consumes_delivery_status(self):
        request = RequestFactory().get('/accounts/register/complete/')
        request.session = {'registration_email_sent': False}
        view = RegistrationCompleteView()
        view.setup(request)

        context = view.get_context_data()

        self.assertFalse(context['registration_email_sent'])
        self.assertNotIn('registration_email_sent', request.session)
