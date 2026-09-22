from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('stream', '0008_servicefetchstate_outcome_timestamps'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicefetchstate',
            name='consecutive_failures',
            field=models.PositiveIntegerField(
                default=0, verbose_name='Consecutive failures'
            ),
        ),
        migrations.AddField(
            model_name='servicefetchstate',
            name='failure_category',
            field=models.CharField(
                blank=True, max_length=32, verbose_name='Failure category'
            ),
        ),
        migrations.AddField(
            model_name='servicefetchstate',
            name='failure_kind',
            field=models.CharField(
                blank=True,
                choices=[('retryable', 'Retryable'), ('terminal', 'Terminal')],
                max_length=16,
                verbose_name='Failure kind',
            ),
        ),
    ]
