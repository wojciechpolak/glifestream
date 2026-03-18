#!/bin/bash

export DJANGO_SETTINGS_MODULE=run.settings_docker

python manage.py migrate --run-syncdb --fake-initial

python manage.py shell <<EOL
from glifestream.stream.models import Service
if not Service.objects.exists():
    print('Loading initial data...')
    from django.core.management import call_command
    call_command('loaddata', 'glifestream/stream/fixtures/initial_data.json')
EOL

python manage.py collectstatic --no-input
python worker.py --init-files-dirs
chgrp -R users /app/static/ && chmod -R g+w /app/static

python manage.py create_initial_user

/usr/local/bin/supervisord -c /etc/supervisord.conf
