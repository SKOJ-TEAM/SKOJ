# coding=utf-8
import re
import json
from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import get_default_password_validators, validate_password
from django.core.exceptions import ValidationError
from django.forms import ModelChoiceField
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext, gettext_lazy as _
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from registration import signals
from registration.backends.default.views import (ActivationView as OldActivationView,
                                                 RegistrationView as OldRegistrationView)
from registration.forms import RegistrationForm
from judge.models import Language, Profile

from judge.utils.recaptcha import ReCaptchaField, ReCaptchaWidget
from judge.utils.subscription import Subscription, newsletter_id
from judge.widgets import Select2Widget



bad_mail_regex = list(map(re.compile, settings.BAD_MAIL_PROVIDER_REGEX))

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
    # organizations = SortedMultipleChoiceField(queryset=Organization.objects.filter(is_open=True),
    #                                           label=_('Organizations'), required=False,
    #                                           widget=Select2MultipleWidget(attrs={'style': 'width:100%'}))

    if newsletter_id is not None:
        newsletter = forms.BooleanField(label=_('Subscribe to newsletter?'), initial=True, required=False)

    if ReCaptchaField is not None:
        captcha = ReCaptchaField(widget=ReCaptchaWidget())

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
        user = form.save()
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])

        signals.user_registered.send(
            sender=self.__class__,
            user=user,
            request=self.request,
        )

        profile, _ = Profile.objects.get_or_create(user=user, defaults={
            'language': Language.get_default_language(),
        })

        cleaned_data = form.cleaned_data
        user.first_name = cleaned_data['first_name']
        user.save()

        profile.timezone = settings.DEFAULT_USER_TIME_ZONE
        profile.language = cleaned_data['language']
        profile.save()

        if newsletter_id is not None and cleaned_data['newsletter']:
            Subscription(user=user, newsletter_id=newsletter_id, subscribed=True).save()
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


def social_auth_error(request):
    return render(request, 'generic-message.html', {
        'title': gettext('Authentication failure'),
        'message': request.GET.get('message'),
    })
