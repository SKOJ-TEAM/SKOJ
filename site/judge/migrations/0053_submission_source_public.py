from django.db import migrations, models


def protect_staff_submissions(apps, schema_editor):
    Submission = apps.get_model('judge', 'Submission')
    Submission.objects.using(schema_editor.connection.alias).filter(user__user__is_staff=True).update(
        is_source_public=False,
    )


class Migration(migrations.Migration):
    dependencies = [('judge', '0052_rename_promotion_to_challenge')]

    operations = [
        migrations.AddField(
            model_name='submission',
            name='is_source_public',
            field=models.BooleanField(default=True, verbose_name='코드 공개'),
        ),
        migrations.RunPython(protect_staff_submissions, migrations.RunPython.noop),
    ]
