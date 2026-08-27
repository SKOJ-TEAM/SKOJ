# coding=utf-8
import json
import logging
import re
import smtplib

from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import get_default_password_validators, validate_password
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import ModelChoiceField
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext, gettext_lazy as _
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView
from registration import signals
from registration.backends.default.views import (ActivationView as OldActivationView,
                                                 RegistrationView as OldRegistrationView)
from registration.forms import RegistrationForm
from registration.models import RegistrationProfile
from judge.models import Campus, Cohort, Language, Profile, TrainingClass

from judge.utils.recaptcha import ReCaptchaField, ReCaptchaWidget
from judge.utils.subscription import Subscription, newsletter_id
from judge.widgets import Select2Widget



bad_mail_regex = list(map(re.compile, settings.BAD_MAIL_PROVIDER_REGEX))
logger = logging.getLogger(__name__)


TRAINING_CLASS_RANGES = {
    'gwangju': range(1, 5),
    'pangyo': range(1, 7),
    'ulsan': range(1, 5),
}
ENABLED_REGISTRATION_CAMPUSES = {'gwangju'}


class CampusSelect2Widget(Select2Widget):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs']['data-campus-code'] = instance.code
        return option

def _validate_registration_username(username):
    errors = []

    if not username:
        return errors

    field = CustomRegistrationForm.base_fields['username']
    try:
        field.clean(username)
    except ValidationError as exc:
        errors.extend(exc.messages)
        return errors

    return errors


def _validate_registration_email(email):
    errors = []

    if not email:
        return '', errors

    field = CustomRegistrationForm.base_fields['email']
    try:
        email = field.clean(email)
    except ValidationError as exc:
        return '', exc.messages

    if User.objects.filter(email__iexact=email).exists():
        errors.append(gettext('해당 이메일은 이미 존재하는 이메일입니다.'))
        return email, errors

    domain = email.split('@')[-1].lower()
    if domain in settings.BAD_MAIL_PROVIDERS or any(regex.match(domain) for regex in bad_mail_regex):
        errors.append(gettext('Your email provider is not allowed due to history of abuse. Please use a reputable email provider.'))

    return email, errors


def _validate_registration_password(password, username='', first_name='', email=''):
    if not password:
        return []

    validators = get_default_password_validators()
    temp_user = User(username=username or '', first_name=first_name or '', email=email or '')

    try:
        validate_password(password, user=temp_user, password_validators=validators)
    except ValidationError as exc:
        return exc.messages

    return []

@csrf_exempt
def validate_password_method(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            password = data.get('password', '')
            username = data.get('username', '')
            first_name = data.get('first_name', '')
            email = data.get('email', '')
            errors = _validate_registration_password(
                password,
                username=username,
                first_name=first_name,
                email=email,
            )
            if not errors:
                return JsonResponse({'is_valid': True, 'errors': []})
            return JsonResponse({'errors': errors})
        except Exception:
            return JsonResponse({'errors': ['Internal Server Error']}, status=500)
    return JsonResponse({'errors': ['Invalid request method.']})


@csrf_exempt
def validate_registration_method(request):
    if request.method != 'POST':
        return JsonResponse({'errors': ['Invalid request method.']}, status=405)

    try:
        data = json.loads(request.body)
    except (TypeError, ValueError):
        return JsonResponse({'errors': ['Invalid request body.']}, status=400)

    username = (data.get('username') or '').strip()
    first_name = (data.get('first_name') or '').strip()
    email = (data.get('email') or '').strip()
    password1 = data.get('password1') or ''
    password2 = data.get('password2') or ''

    email, email_errors = _validate_registration_email(email)
    password1_errors = _validate_registration_password(
        password1,
        username=username,
        first_name=first_name,
        email=email,
    )

    errors = {
        'username': _validate_registration_username(username),
        'email': email_errors,
        'password1': password1_errors,
        'password2': [],
    }

    if password2 and password1 != password2:
        errors['password2'].append('비밀번호가 일치하지 않습니다.')

    return JsonResponse({'errors': errors})


class CustomRegistrationForm(RegistrationForm):
    username = forms.RegexField(
        regex=r'^[A-Za-z0-9_]+$',
        max_length=150,
        label=_('아이디'),
        error_messages={'invalid': '아이디는 영문자, 숫자, 밑줄(_)만 사용할 수 있습니다.'},
        widget=forms.TextInput(attrs={'placeholder': _('아이디'), 'autocomplete': 'username'})
    )

    # 이름
    first_name = forms.CharField(
        max_length=30,
        label=_('first name'),
        # label=_('FirstName'),
        widget=forms.TextInput(attrs={'placeholder': '이름'})
    )

    email = forms.EmailField(
        label=_('Email'),
        widget=forms.EmailInput(attrs={'placeholder': _('이메일'), 'autocomplete': 'email'}),
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': _('비밀번호'), 'maxlength': '100', 'autocomplete': 'off'}),
        label=_('Password')
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': _('비밀번호 확인'), 'maxlength': '100', 'autocomplete': 'off'}),
        label=_('Password Confirmation')
    )
    language = ModelChoiceField(queryset=Language.objects.all(), label=_('Preferred language'), empty_label=None,
                                widget=Select2Widget(attrs={'style': 'width:100%', 'data-maximum-input-length': '50'}))
    cohort = ModelChoiceField(queryset=Cohort.objects.none(), label=_('기수'), empty_label=_('기수 선택'),
                              widget=Select2Widget(attrs={'style': 'width:100%'}))
    campus = ModelChoiceField(queryset=Campus.objects.none(), label=_('캠퍼스'), empty_label=_('캠퍼스 선택'),
                              widget=CampusSelect2Widget(attrs={'style': 'width:100%'}))
    training_class = forms.TypedChoiceField(
        choices=(('', _('캠퍼스를 먼저 선택해 주세요')),),
        coerce=int,
        empty_value=None,
        label=_('반'),
        widget=forms.Select(attrs={'style': 'width:100%'}),
    )
    # organizations = SortedMultipleChoiceField(queryset=Organization.objects.filter(is_open=True),
    #                                           label=_('Organizations'), required=False,
    #                                           widget=Select2MultipleWidget(attrs={'style': 'width:100%'}))

    if newsletter_id is not None:
        newsletter = forms.BooleanField(label=_('Subscribe to newsletter?'), initial=True, required=False)

    if ReCaptchaField is not None:
        captcha = ReCaptchaField(widget=ReCaptchaWidget())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cohort'].queryset = Cohort.objects.filter(is_active=True).order_by('-number')
        self.fields['campus'].queryset = Campus.objects.filter(is_active=True).order_by('name')
        class_numbers = sorted({number for numbers in TRAINING_CLASS_RANGES.values() for number in numbers})
        self.fields['training_class'].choices = [('', _('캠퍼스를 먼저 선택해 주세요'))] + [
            (number, _('%(number)s반') % {'number': number}) for number in class_numbers
        ]

    def clean(self):
        cleaned_data = super().clean()
        cohort = cleaned_data.get('cohort')
        campus = cleaned_data.get('campus')
        class_number = cleaned_data.get('training_class')
        if not cohort or not campus or class_number is None:
            return cleaned_data

        allowed_numbers = TRAINING_CLASS_RANGES.get(campus.code, ())
        if class_number not in allowed_numbers:
            raise forms.ValidationError(_('선택한 캠퍼스에서 운영하지 않는 반입니다.'))

        if campus.code not in ENABLED_REGISTRATION_CAMPUSES:
            raise forms.ValidationError(
                _('%(campus)s 캠퍼스는 아직 회원가입을 지원하지 않습니다. 관리자에게 문의해 주세요.') % {
                    'campus': campus.name,
                },
            )

        try:
            cleaned_data['training_class'] = TrainingClass.objects.get(
                cohort=cohort,
                campus=campus,
                number=class_number,
                is_active=True,
            )
        except TrainingClass.DoesNotExist:
            raise forms.ValidationError(_('선택한 반을 등록할 수 없습니다. 관리자에게 문의해 주세요.'))
        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(gettext('해당 이메일은 이미 존재하는 이메일입니다.'))
        domain = email.split('@')[-1].lower()
        if (domain in settings.BAD_MAIL_PROVIDERS or
                any(regex.match(domain) for regex in bad_mail_regex)):
            raise forms.ValidationError(gettext('Your email provider is not allowed due to history of abuse. '
                                                'Please use a reputable email provider.'))
        return email

    # def clean_organizations(self):
    #     organizations = self.cleaned_data.get('organizations') or []
    #     max_orgs = settings.DMOJ_USER_MAX_ORGANIZATION_COUNT
    #     if len(organizations) > max_orgs:
    #         raise forms.ValidationError(ngettext('You may not be part of more than {count} public organization.',
    #                                              'You may not be part of more than {count} public organizations.',
    #                                              max_orgs).format(count=max_orgs))
    #     return self.cleaned_data['organizations']


class RegistrationView(OldRegistrationView):
    title = _('Register')
    form_class = CustomRegistrationForm
    template_name = 'registration/registration_form.html'

    def get_context_data(self, **kwargs):
        if 'title' not in kwargs:
            kwargs['title'] = self.title
        tzmap = settings.TIMEZONE_MAP
        kwargs['TIMEZONE_MAP'] = tzmap or 'http://momentjs.com/static/img/world.png'
        kwargs['TIMEZONE_BG'] = settings.TIMEZONE_BG if tzmap else '#4E7CAD'
        kwargs['password_validators'] = get_default_password_validators()
        kwargs['tos_url'] = settings.TERMS_OF_SERVICE_URL
        kwargs['validate_password_url'] = reverse('validate_password')
        kwargs['validate_registration_url'] = reverse('validate_registration')
        return super(RegistrationView, self).get_context_data(**kwargs)

    def register(self, form):
        cleaned_data = form.cleaned_data
        with transaction.atomic():
            user = form.save(commit=False)
            user.first_name = cleaned_data['first_name']
            user.is_active = False
            user.save()

            registration_profile = RegistrationProfile.objects.create_profile(user)
            profile, _ = Profile.objects.get_or_create(user=user, defaults={
                'language': Language.get_default_language(),
            })
            profile.timezone = settings.DEFAULT_USER_TIME_ZONE
            profile.language = cleaned_data['language']
            profile.training_class = cleaned_data['training_class']
            profile.save()

            if newsletter_id is not None and cleaned_data['newsletter']:
                Subscription(user=user, newsletter_id=newsletter_id, subscribed=True).save()

        signals.user_registered.send(
            sender=self.__class__,
            user=user,
            request=self.request,
        )

        try:
            registration_profile.send_activation_email(
                site=get_current_site(self.request),
                request=self.request,
            )
        except (OSError, smtplib.SMTPException):
            logger.exception('Failed to send registration activation email for user %s', user.pk)
            self.request.session['registration_email_sent'] = False
        else:
            self.request.session['registration_email_sent'] = True
        return user


    def get_initial(self, *args, **kwargs):
        initial = super(RegistrationView, self).get_initial(*args, **kwargs)
        initial['timezone'] = settings.DEFAULT_USER_TIME_ZONE
        initial['language'] = Language.objects.get(key=settings.DEFAULT_USER_LANGUAGE)
        return initial
     

class ActivationView(OldActivationView):
    title = _('Activation Key Invalid')
    template_name = 'registration/activate.html'

    def get_context_data(self, **kwargs):
        if 'title' not in kwargs:
            kwargs['title'] = self.title
        return super(ActivationView, self).get_context_data(**kwargs)


class RegistrationCompleteView(TemplateView):
    template_name = 'registration/registration_complete.html'
    title = _('회원가입 완료')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.title
        context['registration_email_sent'] = self.request.session.pop('registration_email_sent', None)
        return context


def social_auth_error(request):
    return render(request, 'generic-message.html', {
        'title': gettext('Authentication failure'),
        'message': request.GET.get('message'),
    })
