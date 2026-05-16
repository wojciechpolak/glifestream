from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stream', '0007_fetch_worker'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicefetchstate',
            name='last_failed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Last failed at'),
        ),
        migrations.AddField(
            model_name='servicefetchstate',
            name='last_succeeded_at',
            field=models.DateTimeField(
                blank=True, null=True, verbose_name='Last succeeded at'
            ),
        ),
    ]
