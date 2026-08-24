from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0037_skala_training_structure'),
    ]

    operations = [
        # MariaDB reused the composite unique index below for the school_id foreign key.
        # Give the foreign key its own index before dropping the unique constraint.
        # The temporary index is removed automatically when school_id is dropped.
        migrations.RunSQL(
            sql='CREATE INDEX tmp_profile_school_fk ON judge_profile (school_id)',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RemoveConstraint(
            model_name='profile',
            name='unique_school_student_number',
        ),
        migrations.RemoveField(model_name='profile', name='department'),
        migrations.RemoveField(model_name='profile', name='school'),
        migrations.RemoveField(model_name='profile', name='student_number'),
        migrations.RemoveField(model_name='contest', name='school'),
        migrations.DeleteModel(name='Department'),
        migrations.DeleteModel(name='School'),
    ]
