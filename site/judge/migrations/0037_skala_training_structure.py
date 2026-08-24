from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


def create_campuses(apps, schema_editor):
    Campus = apps.get_model('judge', 'Campus')
    for code, name in (
        ('gwangju', '광주'),
        ('pangyo', '판교'),
        ('ulsan', '울산'),
    ):
        Campus.objects.get_or_create(code=code, defaults={'name': name, 'is_active': True})


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0036_alter_algorithmguide_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='Campus',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(max_length=20, unique=True, verbose_name='캠퍼스 코드')),
                ('name', models.CharField(max_length=30, unique=True, verbose_name='캠퍼스')),
                ('is_active', models.BooleanField(default=True, verbose_name='활성 여부')),
            ],
            options={
                'verbose_name': '캠퍼스',
                'verbose_name_plural': '캠퍼스',
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='Cohort',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.PositiveIntegerField(unique=True, validators=[django.core.validators.MinValueValidator(1)], verbose_name='기수')),
                ('is_active', models.BooleanField(default=True, verbose_name='활성 여부')),
            ],
            options={
                'verbose_name': '기수',
                'verbose_name_plural': '기수',
                'ordering': ('-number',),
            },
        ),
        migrations.CreateModel(
            name='TrainingClass',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)], verbose_name='반')),
                ('is_active', models.BooleanField(default=True, verbose_name='활성 여부')),
                ('campus', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                             related_name='training_classes', to='judge.campus',
                                             verbose_name='캠퍼스')),
                ('cohort', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                             related_name='training_classes', to='judge.cohort',
                                             verbose_name='기수')),
            ],
            options={
                'verbose_name': '반',
                'verbose_name_plural': '반',
                'ordering': ('-cohort__number', 'campus__name', 'number'),
            },
        ),
        migrations.AddConstraint(
            model_name='trainingclass',
            constraint=models.UniqueConstraint(fields=('cohort', 'campus', 'number'),
                                                name='unique_training_class'),
        ),
        migrations.AddConstraint(
            model_name='cohort',
            constraint=models.CheckConstraint(check=models.Q(number__gte=1), name='positive_cohort_number'),
        ),
        migrations.AddConstraint(
            model_name='trainingclass',
            constraint=models.CheckConstraint(check=models.Q(number__gte=1), name='positive_training_class_number'),
        ),
        migrations.RunPython(create_campuses, migrations.RunPython.noop),
        migrations.AddField(
            model_name='profile',
            name='training_class',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='members', to='judge.trainingclass', verbose_name='반'),
        ),
        migrations.AddField(
            model_name='contest',
            name='allowed_classes',
            field=models.ManyToManyField(blank=True, help_text='비워두면 모든 반에 공개됩니다.',
                                         related_name='contests', to='judge.TrainingClass', verbose_name='허용 반'),
        ),
    ]
