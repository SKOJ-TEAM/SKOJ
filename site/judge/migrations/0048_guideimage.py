from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import judge.models.guide


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('judge', '0047_five_tier_gamification'),
    ]

    operations = [
        migrations.CreateModel(
            name='GuideImage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=150, verbose_name='자료명')),
                ('alt_text', models.CharField(blank=True, max_length=200, verbose_name='대체 텍스트')),
                ('image', models.ImageField(upload_to=judge.models.guide.guide_image_upload_path, validators=[judge.models.guide.validate_guide_image], verbose_name='이미지')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='등록일')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='guide_images', to=settings.AUTH_USER_MODEL, verbose_name='업로더')),
            ],
            options={
                'verbose_name': '사진 자료',
                'verbose_name_plural': '사진 자료',
                'ordering': ('-created_at', '-id'),
            },
        ),
    ]
