from django.test import TestCase, override_settings


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class HomePageTestCase(TestCase):
    def setUp(self):
        self.response = self.client.get('/')

    def test_home_renders(self):
        self.assertEqual(self.response.status_code, 200)

    def test_site_long_name_in_og_meta(self):
        self.assertContains(self.response, 'SKALA Online Judge')

    def test_brand_tokens_defined(self):
        content = self.response.content.decode()
        self.assertIn('--brand-red: #EA002C;', content)
        self.assertIn('--brand-orange: #F47725;', content)

    def test_primary_color_uses_brand_red(self):
        content = self.response.content.decode()
        self.assertIn('--primary-color: var(--brand-red);', content)

    def test_footer_removed(self):
        content = self.response.content.decode()
        self.assertNotIn('<footer>', content)
        self.assertNotIn('서비스 표준약관', content)
        self.assertNotIn('JBNU and ALPS', content)

    def test_site_icon_is_displayed_next_to_text_logo(self):
        content = self.response.content.decode()
        self.assertIn('href="/static/icons/favicon-32x32.png?v=20260830"', content)
        self.assertIn('src="/static/icons/nav-icon-64x64.png"', content)
        self.assertIn('class="site-logo-icon"', content)
        self.assertIn('<span>SKOJ</span>', content)
        self.assertNotIn('Litmuslogosvg', content)
        self.assertNotIn('data-site-logo', content)

    def test_active_nav_uses_brand_colors(self):
        content = self.response.content.decode()
        self.assertIn('border-bottom: 3px solid var(--brand-orange)', content)

    def test_primary_navigation_order_excludes_assignments(self):
        content = self.response.content.decode()
        labels = ('PROBLEMS', 'USERS', 'STATUS', 'ABOUT')
        positions = [content.index('>%s</a>' % label) for label in labels]

        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('>ASSIGNMENTS</a>', content)
        self.assertNotIn('>CONTESTS</a>', content)


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class HomeHeroTestCase(TestCase):
    def setUp(self):
        self.response = self.client.get('/')

    def test_hero_copy(self):
        self.assertContains(self.response, 'SKALA Online Judge')
        self.assertContains(
            self.response, '프로그래밍 문제를 풀고 온라인으로 채점받을 수 있는 곳입니다.')

    def test_stats_banner_removed(self):
        content = self.response.content.decode()
        self.assertNotIn('id="home-stats"', content)
        self.assertNotIn('class="home-stat"', content)

    def test_old_home_markup_removed(self):
        content = self.response.content.decode()
        self.assertNotIn('ONLINE JUDGE', content)
        self.assertNotIn('main_logo.png', content)
        self.assertNotIn('forms.gle', content)
