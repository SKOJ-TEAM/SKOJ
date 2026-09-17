from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.html import format_html

from judge.jinja2.gravatar import gravatar
from judge.models import Campus, Cohort, TrainingClass


User = get_user_model()


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class UserListViewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_superuser(
            username='user-list-viewer',
            email='viewer@example.com',
            password='test-password',
            first_name='목록 관리자',
        )
        cls.normal = User.objects.create_user(username='normal-login', first_name='홍길동')
        cls.staff = User.objects.create_user(username='staff-login', first_name='김교수', is_staff=True)
        cls.unnamed = User.objects.create_user(username='unnamed-login', first_name='')

    def setUp(self):
        self.client.force_login(self.viewer)

    def assertAvatarNameLink(self, response, user):
        self.assertContains(response, format_html(
            '<a class="profile-avatar-name" href="{}" aria-label="{} 프로필 보기">'
            '<img class="profile-avatar" src="{}" alt="" width="32" height="32" '
            'loading="lazy" decoding="async">{}</a>',
            reverse('user_page', args=(user.username,)), user.first_name or '사용자',
            gravatar(user.profile, 32), user.first_name,
        ), html=True)

    def test_list_displays_names_for_all_user_types(self):
        response = self.client.get(reverse('user_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<th class="header first_name">이름</th>', html=True)
        self.assertAvatarNameLink(response, self.normal)
        self.assertAvatarNameLink(response, self.staff)
        self.assertNotContains(response, '>normal-login</a>')
        self.assertNotContains(response, '>staff-login</a>')
        self.assertNotContains(response, 'class="user-name"')

    def test_list_leaves_missing_name_blank_without_username_fallback(self):
        response = self.client.get(reverse('user_list'))

        self.assertAvatarNameLink(response, self.unnamed)
        self.assertNotContains(response, '>unnamed-login</a>')

    def test_list_escapes_name_text(self):
        self.normal.first_name = '<script>alert(1)</script>'
        self.normal.save(update_fields=('first_name',))

        response = self.client.get(reverse('user_list'))

        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_search_uses_name_and_updates_placeholder(self):
        response = self.client.get(reverse('user_list'), {'search': '홍길'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'placeholder="이름 검색"')
        self.assertContains(response, 'id="user-normal-login"')
        self.assertNotContains(response, 'id="user-staff-login"')

    def test_search_does_not_match_username(self):
        response = self.client.get(reverse('user_list'), {'search': 'normal-login'})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="user-normal-login"')

    def test_own_row_is_pinned_on_each_page_with_actual_rank(self):
        for index in range(21):
            user = User.objects.create_user(username='ahead-%s' % index)
            user.profile.performance_points = 100
            user.profile.save(update_fields=('performance_points',))
        for page in (1, 2):
            response = self.client.get(reverse('user_list'), {'page': page})
            rows = response.context_data['users']
            self.assertEqual((rows[0][0], rows[0][1].pk), (22, self.viewer.profile.pk))
            self.assertEqual(sum(user.pk == self.viewer.profile.pk for _, user in rows), page)
            expected_ranks = list(range(1, 21)) if page == 1 else list(range(21, 26))
            self.assertEqual([rank for rank, _ in rows[1:]], expected_ranks)
            self.assertContains(response, 'class="current-user-row"', count=1)
            self.assertContains(response, 'class="current-user-badge"', count=1)
            self.assertContains(response, 'id="current-user-summary"', count=1)
            if page == 2:
                self.assertContains(response, 'id="user-user-list-viewer"', count=1)
            self.assertEqual(response.context_data['paginator'].count, 25)

    def test_search_does_not_pin_nonmatching_viewer(self):
        response = self.client.get(reverse('user_list'), {'search': '홍길'})
        self.assertNotContains(response, 'id="user-user-list-viewer"')
        self.assertNotContains(response, 'class="current-user-row"')

    def test_unlisted_viewer_is_not_added(self):
        self.viewer.profile.is_unlisted = True
        self.viewer.profile.save(update_fields=('is_unlisted',))
        response = self.client.get(reverse('user_list'))
        self.assertNotContains(response, 'id="user-user-list-viewer"')
        self.assertNotContains(response, 'class="current-user-row"')

    def test_pinned_row_preserves_training_class_scope(self):
        training_class = TrainingClass.objects.create(
            cohort=Cohort.objects.create(number=99),
            campus=Campus.objects.create(code='pinning-campus', name='테스트'), number=1,
        )
        self.normal.profile.training_class = training_class
        self.normal.profile.save(update_fields=('training_class',))
        self.client.force_login(self.normal)
        response = self.client.get(reverse('user_list'))
        self.assertEqual([user.pk for _, user in response.context_data['users']], [self.normal.profile.pk] * 2)
        self.assertContains(response, 'class="current-user-row"', count=1)

    def test_anonymous_viewer_still_requires_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(reverse('user_list')), reverse('auth_login'),
                             fetch_redirect_response=False)
