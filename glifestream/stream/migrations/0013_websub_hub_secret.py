"""Store the secret the hub was given, not the one it was cut from.

From 2026-03 `subscribe()` stored the whole 32-character digest while it sent
the hub its first 8 characters, and a plain http hub none, so no payload
from that hub ever passed the signature check. Each such row gets the
secret its hub signs with.
"""

from django.db import migrations
from django.db.models.functions import Length


def store_hub_secret(apps, schema_editor):
    WebSub = apps.get_model('stream', 'WebSub')
    for sub in WebSub.objects.annotate(secret_len=Length('secret')).filter(
        secret_len__gt=8
    ):
        sub.secret = sub.secret[0:8] if 'https://' in sub.hub else None
        sub.save(update_fields=['secret'])


class Migration(migrations.Migration):
    dependencies = [
        ('stream', '0012_service_public_no_index'),
    ]

    operations = [
        migrations.RunPython(store_hub_secret, migrations.RunPython.noop),
    ]
