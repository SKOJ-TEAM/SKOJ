import json

from django.db import migrations, models
import django.db.models.deletion


def rename_permissions(apps, schema_editor, old_prefix, new_prefix):
    # Keep permission IDs so direct user grants and group grants remain intact.
    Permission = apps.get_model('auth', 'Permission')
    for suffix in ('exam', 'attempt', 'attemptproblem'):
        old_model = old_prefix + suffix
        new_model = new_prefix + suffix
        permissions = Permission.objects.using(schema_editor.connection.alias).filter(
            content_type__app_label='judge', content_type__model__in=(old_model, new_model),
        )
        for action in ('add', 'change', 'delete', 'view'):
            permissions.filter(codename=action + '_' + old_model).update(codename=action + '_' + new_model)


def rename_revision_fields(apps, schema_editor, old_prefix, new_prefix):
    # Reversion stores field/model names in JSON; preserve their meaning on restore.
    Version = apps.get_model('reversion', 'Version')
    model_names = {old_prefix + suffix: new_prefix + suffix for suffix in ('exam', 'attempt', 'attemptproblem')}
    versions = Version.objects.using(schema_editor.connection.alias).filter(
        content_type__app_label='judge',
        content_type__model__in=['problem', *model_names, *model_names.values()],
        format='json',
    )
    for version in versions.iterator(chunk_size=500):
        data = json.loads(version.serialized_data)
        changed = False
        for obj in data:
            model_name = obj['model']
            if model_name == 'judge.problem':
                fields = obj['fields']
                for suffix in ('_exam', '_order'):
                    old_field, new_field = old_prefix + suffix, new_prefix + suffix
                    if old_field in fields:
                        fields[new_field] = fields.pop(old_field)
                        changed = True
            elif model_name.startswith('judge.') and model_name[6:] in model_names:
                obj['model'] = 'judge.' + model_names[model_name[6:]]
                changed = True
        if changed:
            version.serialized_data = json.dumps(data, ensure_ascii=False)
            version.save(update_fields=('serialized_data',), using=schema_editor.connection.alias)


def forwards(apps, schema_editor):
    rename_permissions(apps, schema_editor, 'promotion', 'challenge')
    rename_revision_fields(apps, schema_editor, 'promotion', 'challenge')


def backwards(apps, schema_editor):
    rename_permissions(apps, schema_editor, 'challenge', 'promotion')
    rename_revision_fields(apps, schema_editor, 'challenge', 'promotion')


class Migration(migrations.Migration):
    dependencies = [
        ('judge', '0051_profile_avatar'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('reversion', '0001_squashed_0004_auto_20160611_1202'),
    ]

    operations = [
        migrations.RenameModel(old_name='PromotionExam', new_name='ChallengeExam'),
        migrations.RenameModel(old_name='PromotionAttempt', new_name='ChallengeAttempt'),
        migrations.RenameModel(old_name='PromotionAttemptProblem', new_name='ChallengeAttemptProblem'),
        migrations.RenameField(model_name='problem', old_name='promotion_exam', new_name='challenge_exam'),
        migrations.RenameField(model_name='problem', old_name='promotion_order', new_name='challenge_order'),
        migrations.AlterField(
            model_name='challengeattempt', name='profile',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name='challenge_attempts',
                to='judge.profile', verbose_name='사용자 프로필',
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
