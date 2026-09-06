from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('judge', '0049_guidecompletion'),
    ]

    operations = [
        migrations.AddField(
            model_name='problem',
            name='group_order',
            field=models.PositiveIntegerField(
                blank=True,
                db_index=True,
                help_text='문제 그룹 관리자에서 설정하는 학습 순서입니다.',
                null=True,
                verbose_name='그룹 내 노출 순서',
            ),
        ),
    ]
