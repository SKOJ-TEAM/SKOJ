from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from judge.models import ProfileGamification, Tier


User = get_user_model()


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class RankingViewTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ranking-user', password='test-password')

    def test_anonymous_user_is_redirected(self):
        response = self.client.get(reverse('gamification_ranking'))
        self.assertRedirects(
            response,
            '/accounts/login/?next=/ranking/',
            fetch_redirect_response=False,
        )

    def test_authenticated_user_sees_bronze_tier(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('gamification_ranking'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bronze')

    def test_only_diamond_profiles_appear_in_ranking(self):
        diamond = User.objects.create_user(username='diamond-user')
        ProfileGamification.objects.filter(profile=diamond.profile).update(
            current_tier=Tier.DIAMOND,
            weighted_score=20,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('gamification_ranking'))
        self.assertNotContains(response, 'diamond-user')  # no cohort membership means no cohort ranking

    def test_admin_can_view_global_diamond_ranking_with_difficulty_tiebreak(self):
        admin = User.objects.create_superuser(username='ranking-admin', email='admin@example.com', password='pw')
        gold_heavy = User.objects.create_user(username='gold-heavy')
        diamond_heavy = User.objects.create_user(username='diamond-heavy')
        ProfileGamification.objects.filter(profile=gold_heavy.profile).update(
            current_tier=Tier.DIAMOND, weighted_score=20, gold_solved=5, diamond_solved=1,
        )
        ProfileGamification.objects.filter(profile=diamond_heavy.profile).update(
            current_tier=Tier.DIAMOND, weighted_score=20, gold_solved=1, diamond_solved=2,
        )

        self.client.force_login(admin)
        response = self.client.get(reverse('gamification_ranking'), {'scope': 'all'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'gold-heavy')
        self.assertContains(response, 'diamond-heavy')
        self.assertLess(
            response.content.index(b'diamond-heavy'),
            response.content.index(b'gold-heavy'),
        )
