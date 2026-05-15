from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('stream', '0006_alter_service_api'),
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='fetch_interval_sec',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Optional override for scheduled fetch interval in seconds.',
                null=True,
                verbose_name='Fetch interval (seconds)',
            ),
        ),
        migrations.AddField(
            model_name='service',
            name='next_fetch_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Next fetch at',
            ),
        ),
        migrations.CreateModel(
            name='ServiceFetchState',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('idle', 'Idle'),
                            ('queued', 'Queued'),
                            ('running', 'Running'),
                            ('succeeded', 'Succeeded'),
                            ('failed', 'Failed'),
                        ],
                        default='idle',
                        max_length=16,
                        verbose_name='Status',
                    ),
                ),
                (
                    'trigger',
                    models.CharField(
                        blank=True,
                        choices=[('manual', 'Manual'), ('schedule', 'Schedule')],
                        default='',
                        max_length=16,
                        verbose_name='Trigger',
                    ),
                ),
                (
                    'requested_at',
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name='Requested at',
                    ),
                ),
                (
                    'started_at',
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name='Started at',
                    ),
                ),
                (
                    'finished_at',
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name='Finished at',
                    ),
                ),
                (
                    'last_result',
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name='Last result',
                    ),
                ),
                (
                    'last_error',
                    models.TextField(blank=True, verbose_name='Last error'),
                ),
                (
                    'worker_token',
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name='Worker token',
                    ),
                ),
                (
                    'service',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='fetch_state',
                        to='stream.service',
                        verbose_name='Service',
                    ),
                ),
                (
                    'triggered_by_user',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='service_fetches_triggered',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Triggered by user',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Service fetch state',
                'verbose_name_plural': 'Service fetch states',
                'ordering': ('service',),
            },
        ),
    ]
