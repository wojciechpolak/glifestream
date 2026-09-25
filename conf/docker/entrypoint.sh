#!/bin/bash

# Stop at the first failing step: a container that skipped a migration or
# collectstatic would otherwise start anyway and fail later, far from the cause.
set -e

export DJANGO_SETTINGS_MODULE=run.settings_docker

python manage.py migrate --run-syncdb --fake-initial

python manage.py load_initial_data

python manage.py collectstatic --no-input
python worker.py --init-files-dirs
chgrp -R users /app/static/ && chmod -R g+w /app/static

python manage.py create_initial_user

/usr/local/bin/supervisord -c /etc/supervisord.conf
