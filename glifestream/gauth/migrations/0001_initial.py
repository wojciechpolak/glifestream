import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('stream', '0004_websub'),
    ]

    operations = [
        migrations.CreateModel(
            name='OAuthClient',
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
                    'identifier',
                    models.CharField(max_length=64, verbose_name='Identifier'),
                ),
                ('secret', models.CharField(max_length=128, verbose_name='Secret')),
                (
                    'phase',
                    models.PositiveSmallIntegerField(default=0, verbose_name='Phase'),
                ),
                (
                    'token',
                    models.CharField(
                        blank=True, max_length=64, null=True, verbose_name='Token'
                    ),
                ),
                (
                    'token_secret',
                    models.CharField(
                        blank=True,
                        max_length=128,
                        null=True,
                        verbose_name='Token secret',
                    ),
                ),
                (
                    'request_token_url',
                    models.URLField(
                        blank=True, null=True, verbose_name='Request Token URL'
                    ),
                ),
                (
                    'access_token_url',
                    models.URLField(
                        blank=True, null=True, verbose_name='Access Token URL'
                    ),
                ),
                (
                    'authorize_url',
                    models.URLField(
                        blank=True, null=True, verbose_name='Authorize URL'
                    ),
                ),
                (
                    'service',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='stream.service',
                        verbose_name='Service',
                    ),
                ),
            ],
            options={
                'verbose_name': 'OAuth',
                'verbose_name_plural': 'OAuth',
                'ordering': ('service',),
            },
        ),
    ]
