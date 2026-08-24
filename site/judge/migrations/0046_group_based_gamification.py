from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('judge', '0045_unify_problem_taxonomy'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='problem',
            name='exclusive_problem_gamification_role',
        ),
        migrations.RemoveField(
            model_name='problem',
            name='gamification_cluster',
        ),
        migrations.RemoveConstraint(
            model_name='difficultycluster',
            name='unique_tier_problem_group_cluster',
        ),
        migrations.AddConstraint(
            model_name='difficultycluster',
            constraint=models.UniqueConstraint(
                fields=('problem_group',),
                name='unique_gamification_problem_group_cluster',
            ),
        ),
    ]
