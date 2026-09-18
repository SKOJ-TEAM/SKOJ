from django.db import migrations


def create_campus_classes(apps, schema_editor):
    Campus = apps.get_model('judge', 'Campus')
    Cohort = apps.get_model('judge', 'Cohort')
    TrainingClass = apps.get_model('judge', 'TrainingClass')
    for code, maximum in (('pangyo', 6), ('ulsan', 4)):
        campus = Campus.objects.filter(code=code, is_active=True).first()
        if campus is None:
            continue
        for cohort in Cohort.objects.filter(is_active=True):
            for number in range(1, maximum + 1):
                TrainingClass.objects.get_or_create(cohort=cohort, campus=campus, number=number)


class Migration(migrations.Migration):
    dependencies = [('judge', '0053_submission_source_public')]
    operations = [migrations.RunPython(create_campus_classes, migrations.RunPython.noop)]
