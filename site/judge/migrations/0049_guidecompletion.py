from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('judge', '0048_guideimage'),
    ]

    operations = [
        migrations.CreateModel(
            name='GuideCompletion',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('completed_at', models.DateTimeField(auto_now_add=True, verbose_name='완료 시각')),
                ('guide', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='completions',
                    to='judge.algorithmguide',
                    verbose_name='가이드',
                )),
                ('profile', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='guide_completions',
                    to='judge.profile',
                    verbose_name='사용자',
                )),
            ],
            options={
                'verbose_name': '가이드 완료',
                'verbose_name_plural': '가이드 완료',
                'ordering': ('-completed_at', '-id'),
            },
        ),
        migrations.AddConstraint(
            model_name='guidecompletion',
            constraint=models.UniqueConstraint(
                fields=('profile', 'guide'),
                name='unique_profile_guide_completion',
            ),
        ),
    ]
