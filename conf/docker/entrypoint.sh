#!/bin/bash

export DJANGO_SETTINGS_MODULE=run.settings_docker

python manage.py migrate --run-syncdb
python manage.py loaddata glifestream/stream/fixtures/initial_data.json
python manage.py collectstatic --no-input
python worker.py --init-files-dirs
chgrp -R users /app/static/ && chmod -R g+w /app/static

python manage.py shell <<EOL
from django.contrib.auth.models import User
if not User.objects.exists():
    print()
    print('Create super user if you haven\'t yet:')
    print('$ docker exec -it glifestream-app-1 python manage.py createsuperuser')
    print()
EOL

/usr/local/bin/supervisord -c /etc/supervisord.conf
