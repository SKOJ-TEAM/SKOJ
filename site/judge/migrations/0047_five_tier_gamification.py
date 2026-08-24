from django.db import migrations, models


TIER_CHOICES = [
    ('bronze', '브론즈'),
    ('silver', '실버'),
    ('gold', '골드'),
    ('diamond', '다이아몬드'),
    ('master', '마스터'),
]


def update_incomplete_attempt_targets(apps, schema_editor):
    PromotionAttempt = apps.get_model('judge', 'PromotionAttempt')
    next_tier = {
        'bronze': 'silver',
        'silver': 'gold',
        'gold': 'diamond',
        'diamond': 'master',
    }
    for source_tier, target_tier in next_tier.items():
        PromotionAttempt.objects.filter(
            source_tier=source_tier,
            completed_at__isnull=True,
        ).update(target_tier=target_tier)


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0046_group_based_gamification'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="profilegamification",
            options={
                "ordering": (
                    "-weighted_score",
                    "-master_solved",
                    "-diamond_solved",
                    "-gold_solved",
                    "-silver_solved",
                    "-bronze_solved",
                    "profile_id",
                ),
                "verbose_name": "사용자 티어",
                "verbose_name_plural": "사용자 티어",
            },
        ),
        migrations.AddField(
            model_name='profilegamification',
            name='master_solved',
            field=models.PositiveIntegerField(default=0, verbose_name='마스터 풀이 수'),
        ),
        migrations.AddField(
            model_name='profilegamification',
            name='silver_solved',
            field=models.PositiveIntegerField(default=0, verbose_name='실버 풀이 수'),
        ),
        migrations.AlterField(
            model_name='difficultycluster',
            name='tier',
            field=models.CharField(choices=TIER_CHOICES, db_index=True, max_length=10, verbose_name='티어'),
        ),
        migrations.AlterField(
            model_name='profilegamification',
            name='current_tier',
            field=models.CharField(choices=TIER_CHOICES, db_index=True, default='bronze', max_length=10,
                                   verbose_name='현재 티어'),
        ),
        migrations.AlterField(
            model_name='promotionattempt',
            name='source_tier',
            field=models.CharField(choices=TIER_CHOICES, max_length=10, verbose_name='출발 티어'),
        ),
        migrations.AlterField(
            model_name='promotionattempt',
            name='target_tier',
            field=models.CharField(choices=TIER_CHOICES, max_length=10, verbose_name='목표 티어'),
        ),
        migrations.AlterField(
            model_name='promotionexam',
            name='source_tier',
            field=models.CharField(choices=[
                ('bronze', '브론즈 → 실버'),
                ('silver', '실버 → 골드'),
                ('gold', '골드 → 다이아몬드'),
                ('diamond', '다이아몬드 → 마스터'),
            ], db_index=True, max_length=10, verbose_name='출발 티어'),
        ),
        migrations.RunPython(update_incomplete_attempt_targets, migrations.RunPython.noop),
    ]
