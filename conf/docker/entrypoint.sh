#!/bin/bash

# Stop at the first failing step: a container that skipped a migration or
# collectstatic would otherwise start anyway and fail later, far from the cause.
set -e

export DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-run.settings_docker}

# A run/ mounted from an empty directory has none of these yet. An existing
# run/settings_docker.py, your own or the checkout's, is left as it is.
[ -n "$(ls -A /app/run/db 2>/dev/null)" ] || new_db=1
[ -d /app/media/upload ] || new_media=1
mkdir -p /app/run/db /app/run/static/themes /app/run/templates
for file in __init__.py settings_docker.py; do
    [ -e "/app/run/$file" ] || cp "/app/conf/run/$file" /app/run/
done

# The Nginx service reads its configuration from the volume mounted here:
# templates in run/nginx/templates/ if there are any, else the image's.
templates=/app/conf/nginx/templates
if compgen -G '/app/run/nginx/templates/*.template' >/dev/null; then
    templates=/app/run/nginx/templates
fi
rm -f /app/nginx/templates/*
cp "$templates"/*.template /app/nginx/templates/

python manage.py migrate --run-syncdb --fake-initial

python manage.py load_initial_data

python manage.py collectstatic --no-input
python worker.py --init-files-dirs
chgrp -R users /app/static/ && chmod -R g+w /app/static

# Gunicorn runs as www-data: let it write the SQLite database and uploads
# created above. Existing ones keep the permissions they have.
if [ -n "$new_db" ]; then
    chgrp -R users /app/run/db && chmod -R g+w /app/run/db
fi
if [ -n "$new_media" ]; then
    find /app/media -maxdepth 2 -type d -exec chgrp users {} + -exec chmod g+w {} +
fi

python manage.py create_initial_user

/usr/local/bin/supervisord -c /etc/supervisord.conf
