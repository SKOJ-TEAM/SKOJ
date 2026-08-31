import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from judge.models import AlgorithmGuide, Campus, Cohort, GuideCompletion, Language, ProblemGroup, \
    ProfileGamification, PromotionAttempt, PromotionAttemptProblem, PromotionExam, Submission, Tier, TrainingClass
from judge.models.tests.util import CommonDataMixin, create_problem


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

    def test_ranking_page_only_contains_ranking(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('gamification_ranking'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '전체 사용자 랭킹')
        self.assertNotContains(response, '내 티어')
        self.assertNotContains(response, '<h2>승급전</h2>', html=True)

    def test_ranking_displays_name_instead_of_username(self):
        self.user.first_name = '홍길동'
        self.user.save(update_fields=('first_name',))
        self.client.force_login(self.user)

        response = self.client.get(reverse('gamification_ranking'))

        self.assertContains(response, '>홍길동</a>')
        self.assertNotContains(response, '>ranking-user</a>')

    def test_ranking_displays_affiliation_and_hides_tier_solve_columns(self):
        cohort = Cohort.objects.create(number=99)
        campus = Campus.objects.create(code='ranking-campus', name='랭킹캠퍼스')
        training_class = TrainingClass.objects.create(cohort=cohort, campus=campus, number=2)
        self.user.profile.training_class = training_class
        self.user.profile.save(update_fields=('training_class',))
        self.client.force_login(self.user)

        response = self.client.get(reverse('gamification_ranking'))

        self.assertContains(response, '<th class="ranking-affiliation">소속반</th>', html=True)
        self.assertContains(response, '99기 랭킹캠퍼스 2반')
        self.assertNotContains(response, '<th>Diamond</th>', html=True)
        self.assertNotContains(response, '<th>Gold</th>', html=True)
        self.assertNotContains(response, '<th>Bronze</th>', html=True)

    def test_all_tiers_appear_in_global_ranking(self):
        silver = User.objects.create_user(username='silver-user')
        diamond = User.objects.create_user(username='diamond-user')
        master = User.objects.create_user(username='master-user')
        ProfileGamification.objects.filter(profile=silver.profile).update(current_tier=Tier.SILVER)
        ProfileGamification.objects.filter(profile=diamond.profile).update(
            current_tier=Tier.DIAMOND,
            weighted_score=20,
        )
        ProfileGamification.objects.filter(profile=master.profile).update(current_tier=Tier.MASTER)
        self.client.force_login(self.user)
        response = self.client.get(reverse('gamification_ranking'))

        self.assertContains(response, 'ranking-user')
        self.assertContains(response, 'diamond-user')
        self.assertContains(response, '브론즈')
        self.assertContains(response, '실버')
        self.assertContains(response, '다이아몬드')
        self.assertContains(response, '마스터')

    def test_ranking_uses_difficulty_tiebreak(self):
        gold_heavy = User.objects.create_user(username='gold-heavy')
        diamond_heavy = User.objects.create_user(username='diamond-heavy')
        ProfileGamification.objects.filter(profile=gold_heavy.profile).update(
            current_tier=Tier.DIAMOND, weighted_score=20, gold_solved=5, diamond_solved=1,
        )
        ProfileGamification.objects.filter(profile=diamond_heavy.profile).update(
            current_tier=Tier.DIAMOND, weighted_score=20, gold_solved=1, diamond_solved=2,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('gamification_ranking'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'gold-heavy')
        self.assertContains(response, 'diamond-heavy')
        self.assertLess(
            response.content.index(b'diamond-heavy'),
            response.content.index(b'gold-heavy'),
        )

    def test_ranking_orders_by_tier_before_weighted_score(self):
        bronze = User.objects.create_user(username='high-score-bronze')
        diamond = User.objects.create_user(username='low-score-diamond')
        ProfileGamification.objects.filter(profile=bronze.profile).update(
            current_tier=Tier.BRONZE, weighted_score=100,
        )
        ProfileGamification.objects.filter(profile=diamond.profile).update(
            current_tier=Tier.DIAMOND, weighted_score=1,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('gamification_ranking'))

        self.assertLess(
            response.content.index(b'low-score-diamond'),
            response.content.index(b'high-score-bronze'),
        )


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class HomeGamificationCardTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='home-tier-user', password='test-password')

    def test_anonymous_home_hides_gamification_cards(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<section class="home-dashboard"')
        self.assertNotContains(response, '내 티어')
        self.assertContains(response, 'id="nav-theme-toggle"')
        self.assertContains(response, 'class="nav-theme-switch"')
        self.assertContains(response, 'role="switch"')
        self.assertContains(response, 'nav-theme-switch-thumb')
        self.assertNotContains(response, 'home-theme-label')
        self.assertNotContains(response, '랜덤 추천 문제')

    def test_anonymous_home_uses_theme_cookie(self):
        self.client.cookies['site_theme'] = 'dark'

        response = self.client.get(reverse('home'))

        self.assertContains(response, "var theme = 'dark';")

    def test_authenticated_home_shows_tier_and_promotion_cards(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<section class="home-dashboard"')
        self.assertContains(response, '학습 현황')
        self.assertContains(response, '내 티어')
        self.assertContains(response, '<h2>승급전</h2>', html=True)
        self.assertContains(response, reverse('gamification_ranking'))
        self.assertContains(response, '랜덤 추천 문제')

    def test_home_guide_progress_counts_only_published_guides_and_includes_intro(self):
        intro_group = ProblemGroup.objects.create(name='skoj-intro', full_name='SKOJ Intro')
        later_group = ProblemGroup.objects.create(name='later-guide', full_name='후속 학습')
        draft_group = ProblemGroup.objects.create(name='draft-guide', full_name='비공개 그룹')
        intro = AlgorithmGuide.objects.create(
            problem_group=intro_group,
            title='SKOJ Intro', summary='소개', content='소개', is_published=True, order=0,
        )
        first = AlgorithmGuide.objects.create(
            problem_group=later_group,
            title='첫 Guide', summary='첫째', content='첫째', is_published=True, order=10,
        )
        AlgorithmGuide.objects.create(
            problem_group=later_group,
            title='둘째 Guide', summary='둘째', content='둘째', is_published=True, order=11,
        )
        hidden = AlgorithmGuide.objects.create(
            problem_group=later_group,
            title='숨은 Guide', summary='숨김', content='숨김', is_published=False, order=9,
        )
        draft_only = AlgorithmGuide.objects.create(
            problem_group=draft_group,
            title='비공개 Guide', summary='숨김', content='숨김', is_published=False, order=1,
        )
        GuideCompletion.objects.create(profile=self.user.profile, guide=first)
        GuideCompletion.objects.create(profile=self.user.profile, guide=hidden)
        GuideCompletion.objects.create(profile=self.user.profile, guide=draft_only)
        self.client.force_login(self.user)

        response = self.client.get(reverse('home'))

        groups = response.context_data['guide_progress_groups']
        self.assertEqual([item['group'] for item in groups], [intro_group, later_group])
        self.assertEqual(response.context_data['guide_progress_completed'], 1)
        self.assertEqual(response.context_data['guide_progress_total'], 3)
        self.assertEqual(response.context_data['guide_progress_group_counts'], {
            'in_progress': 2, 'completed': 0, 'all': 2,
        })
        self.assertEqual(groups[0]['completed_count'], 0)
        self.assertEqual(groups[0]['total_count'], 1)
        self.assertEqual(groups[1]['completed_count'], 1)
        self.assertEqual(groups[1]['total_count'], 2)
        self.assertContains(response, intro.title)
        self.assertNotContains(response, draft_group.full_name)

    def test_home_guide_progress_preserves_completion_while_guide_is_private(self):
        group = ProblemGroup.objects.create(name='republished-guide', full_name='재공개 학습')
        guide = AlgorithmGuide.objects.create(
            problem_group=group,
            title='재공개 Guide', summary='요약', content='본문', is_published=True, order=1,
        )
        GuideCompletion.objects.create(profile=self.user.profile, guide=guide)
        self.client.force_login(self.user)

        completed_response = self.client.get(reverse('home'))
        self.assertEqual(completed_response.context_data['guide_progress_group_counts']['completed'], 1)

        guide.is_published = False
        guide.save(update_fields=('is_published',))
        private_response = self.client.get(reverse('home'))
        self.assertEqual(private_response.context_data['guide_progress_total'], 0)
        self.assertTrue(GuideCompletion.objects.filter(profile=self.user.profile, guide=guide).exists())

        guide.is_published = True
        guide.save(update_fields=('is_published',))
        republished_response = self.client.get(reverse('home'))
        self.assertEqual(republished_response.context_data['guide_progress_completed'], 1)
        self.assertEqual(republished_response.context_data['guide_progress_group_counts']['completed'], 1)

    def test_home_tabs_have_accessible_defaults_and_connected_panels(self):
        group = ProblemGroup.objects.create(name='accessible-guide', full_name='접근성 학습')
        AlgorithmGuide.objects.create(
            problem_group=group,
            title='접근성 Guide', summary='요약', content='본문', is_published=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('home'))

        self.assertContains(
            response,
            'id="guide-tab-in-progress"\n                                aria-selected="true" '
            'aria-controls="guide-panel-in-progress"',
            html=False,
        )
        self.assertContains(response, 'id="guide-panel-in-progress" role="tabpanel"', html=False)
        self.assertContains(
            response,
            'id="tier-tab-current"\n                                aria-selected="true" '
            'aria-controls="tier-panel-current"',
            html=False,
        )
        self.assertContains(response, 'id="tier-panel-current" role="tabpanel"', html=False)
        self.assertContains(response, 'id="guide-panel-completed" role="tabpanel"', html=False)
        self.assertContains(response, 'id="tier-panel-promotion" role="tabpanel"', html=False)
        self.assertContains(response, 'id="guide-panel-completed" role="tabpanel"', html=False)
        self.assertContains(response, 'hidden', html=False)

    def test_home_mobile_card_order_is_guide_then_tier_then_recommendation(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('home'))
        content = response.content.decode()

        self.assertLess(content.index('학습 현황'), content.index('id="tier-tab-current"'))
        self.assertLess(content.index('id="tier-tab-current"'), content.index('id="recommended-problem"'))
        self.assertIn('@media (max-width: 760px)', content)
        self.assertIn('grid-template-columns: 1fr', content)

    def test_home_recommends_only_an_unsolved_public_problem(self):
        solved = create_problem(code='home-solved', name='이미 푼 문제', is_public=True)
        unsolved = create_problem(code='home-unsolved', name='추천할 문제', is_public=True)
        create_problem(code='home-contest', name='대회 전용 문제', is_public=True, is_contest_problem=True)
        Submission.objects.create(
            user=self.user.profile,
            problem=solved,
            language=Language.get_python3(),
            status='D',
            result='AC',
            points=solved.points,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('home'))

        self.assertContains(response, unsolved.name)
        self.assertContains(response, reverse('problem_detail', args=(unsolved.code,)))
        self.assertContains(response, '?recommend=', html=False)
        self.assertNotContains(response, 'onclick="window.location.reload()"', html=False)
        self.assertNotContains(response, solved.name)
        self.assertNotContains(response, '대회 전용 문제')

    def test_home_shows_completion_message_when_no_unsolved_problem_exists(self):
        solved = create_problem(code='home-only-problem', name='마지막 문제', is_public=True)
        Submission.objects.create(
            user=self.user.profile,
            problem=solved,
            language=Language.get_python3(),
            status='D',
            result='AC',
            points=solved.points,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('home'))

        self.assertContains(response, '공개된 모든 문제를 해결했어요!')
        self.assertNotContains(response, '문제 풀러 가기')

    def test_authenticated_home_prefers_profile_theme_over_cookie(self):
        self.user.profile.site_theme = 'dark'
        self.user.profile.save(update_fields=('site_theme',))
        self.client.cookies['site_theme'] = 'light'
        self.client.force_login(self.user)

        response = self.client.get(reverse('home'))

        self.assertContains(response, "var theme = 'dark';")

    def test_home_theme_toggle_saves_authenticated_profile_theme(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('set_theme'), {'theme': 'dark'})

        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.site_theme, 'dark')


@override_settings(COMPRESS_ENABLED=False, SECURE_SSL_REDIRECT=False)
class PromotionExamProblemManagerTestCase(CommonDataMixin, TestCase):
    def setUp(self):
        self.exam = PromotionExam.objects.create(title='Gold 승급전', source_tier=Tier.BRONZE)
        self.first_problem = create_problem(code='promotion-one', name='첫 번째 문제', is_public=True)
        self.second_problem = create_problem(code='promotion-two', name='두 번째 문제', is_public=True)
        self.contest_problem = create_problem(
            code='promotion-contest', name='대회 문제', is_public=True, is_contest_problem=True,
        )
        self.client.force_login(self.users['superuser'])

    def test_change_page_links_to_problem_manager(self):
        response = self.client.get(reverse('admin:judge_promotionexam_change', args=(self.exam.pk,)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse('admin:judge_promotionexam_problem_manager', args=(self.exam.pk,)),
        )
        self.assertContains(response, '현재 선택된 문제: 0개')
        self.assertNotContains(response, 'name="problems"')

    def test_add_page_saves_exam_then_redirects_to_problem_manager(self):
        add_url = reverse('admin:judge_promotionexam_add')
        add_response = self.client.get(add_url)

        self.assertEqual(add_response.status_code, 200)
        self.assertContains(add_response, '저장 후 문제 관리')

        response = self.client.post(add_url, {
            'title': 'Diamond 승급전',
            'source_tier': Tier.GOLD,
            'is_active': 'on',
            '_manage_problems': '1',
        })

        created_exam = PromotionExam.objects.get(title='Diamond 승급전')
        self.assertRedirects(
            response,
            reverse('admin:judge_promotionexam_problem_manager', args=(created_exam.pk,)),
            fetch_redirect_response=False,
        )

    def test_admin_sidebar_groups_gamification_under_korean_ranking_menu(self):
        ranking_menu = next(item for item in settings.WPADMIN['admin']['custom_menu']
                            if isinstance(item, dict) and item.get('title') == '랭킹')

        self.assertEqual(ranking_menu['icon'], 'fa-trophy')
        self.assertEqual(ranking_menu['model'], 'judge.ProfileGamification')
        self.assertEqual(ranking_menu['children'], [
            'judge.DifficultyCluster',
            'judge.PromotionExam',
            'judge.PromotionAttempt',
        ])
        self.assertEqual(ProfileGamification._meta.verbose_name_plural, '사용자 티어')
        self.assertEqual(PromotionExam._meta.verbose_name_plural, '승급전')

        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '랭킹')
        self.assertContains(response, reverse('admin:judge_profilegamification_changelist'))
        self.assertContains(response, '난이도 클러스터')
        self.assertContains(response, '승급전')
        self.assertContains(response, '승급 기록')

    def test_problem_manager_lists_general_problems_and_excludes_contest_problems(self):
        response = self.client.get(reverse(
            'admin:judge_promotionexam_problem_manager', args=(self.exam.pk,),
        ))

        self.assertEqual(response.status_code, 200)
        problem_tree = json.loads(response.context['problems'])
        nodes = [problem_tree]
        problem_ids = []
        while nodes:
            node = nodes.pop()
            nodes.extend(node.get('children', []))
            if not node.get('is_dir', False):
                problem_ids.append(node['id'])
        self.assertIn(self.first_problem.pk, problem_ids)
        self.assertIn(self.second_problem.pk, problem_ids)
        self.assertNotIn(self.contest_problem.pk, problem_ids)

    def test_problem_manager_updates_exam_assignments(self):
        update_url = reverse('admin:judge_promotionexam_problem_manager_update', args=(self.exam.pk,))
        response = self.client.post(update_url, {
            'selected_items': json.dumps({
                str(self.first_problem.pk): True,
                str(self.second_problem.pk): False,
            }),
        })

        self.assertEqual(response.status_code, 200)
        self.first_problem.refresh_from_db()
        self.second_problem.refresh_from_db()
        self.assertEqual(self.first_problem.promotion_exam, self.exam)
        self.assertIsNone(self.second_problem.promotion_exam)

        response = self.client.post(update_url, {
            'selected_items': json.dumps({
                str(self.first_problem.pk): False,
                str(self.second_problem.pk): True,
            }),
        })

        self.assertEqual(response.status_code, 200)
        self.first_problem.refresh_from_db()
        self.second_problem.refresh_from_db()
        self.assertIsNone(self.first_problem.promotion_exam)
        self.assertEqual(self.second_problem.promotion_exam, self.exam)

    def test_problem_manager_syncs_unfinished_attempt_problem_list(self):
        self.first_problem.promotion_exam = self.exam
        self.first_problem.save(update_fields=('promotion_exam',))
        attempt = PromotionAttempt.objects.create(
            profile=self.users['normal'].profile,
            exam=self.exam,
            source_tier=Tier.BRONZE,
            target_tier=Tier.SILVER,
        )
        PromotionAttemptProblem.objects.create(attempt=attempt, problem=self.first_problem, order=0)

        response = self.client.post(
            reverse('admin:judge_promotionexam_problem_manager_update', args=(self.exam.pk,)),
            {'selected_items': json.dumps({
                str(self.first_problem.pk): True,
                str(self.second_problem.pk): True,
            })},
        )

        self.assertEqual(response.status_code, 200)
        self.assertSetEqual(set(attempt.problems.all()), {self.first_problem, self.second_problem})
