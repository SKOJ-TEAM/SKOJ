from django.db import migrations


def remove_legacy_content_types(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(
        app_label='judge',
        model__in=('school', 'department'),
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0038_remove_legacy_school_structure'),
    ]

    operations = [
        migrations.RunPython(remove_legacy_content_types, migrations.RunPython.noop),
    ]
