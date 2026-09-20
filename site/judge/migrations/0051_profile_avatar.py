from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('judge', '0050_problem_group_order')]

    operations = [
        migrations.AddField(
            model_name='profile', name='avatar',
            field=models.ImageField(blank=True, max_length=255, upload_to='avatars/', verbose_name='프로필 사진'),
        ),
    ]
