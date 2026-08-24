from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('judge', '0034_profile_unique_school_student_number'),
    ]

    operations = [
        migrations.CreateModel(
            name='AlgorithmGuide',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=150, verbose_name='title')),
                ('summary', models.CharField(max_length=300, verbose_name='summary')),
                ('content', models.TextField(verbose_name='content')),
                ('is_published', models.BooleanField(db_index=True, default=False, verbose_name='published')),
                ('order', models.PositiveIntegerField(db_index=True, default=0, verbose_name='order')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='algorithm_guides', to=settings.AUTH_USER_MODEL, verbose_name='created by')),
                ('problem_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='algorithm_guides', to='judge.problemtype', verbose_name='algorithm tag')),
            ],
            options={
                'verbose_name': 'algorithm guide',
                'verbose_name_plural': 'algorithm guides',
                'ordering': ('order', 'title', 'id'),
            },
        ),
    ]
