from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0035_algorithmguide'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='algorithmguide',
            options={
                'ordering': ('order', 'title', 'id'),
                'verbose_name': '가이드',
                'verbose_name_plural': '가이드',
            },
        ),
    ]
