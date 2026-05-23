gLifestream -- INSTALL
Copyright (C) 2009-2026 Wojciech Polak

Overview
========

This guide is the primary reference for:

- local development and first-run setup
- Docker deployment
- non-Docker deployment and production hardening

gLifestream is a Django application with a long-lived background worker.
In production you should plan for:

- a persistent database
- persistent `run/` and media directories
- a foreground web process such as Gunicorn behind a reverse proxy
- a separate long-lived `worker.py --daemon` process


Requirements
============

- Python 3.12 or newer
- A database supported by Django (SQLite, MySQL, PostgreSQL, and others supported by Django)
- [uv](https://docs.astral.sh/uv/) for dependency management
- `gettext` if you need to run `compilemessages`

Install dependencies with:

```shell
uv sync
```


Local Development / First Run
=============================

1. Change into the project directory.
2. Copy `.env.example` to `.env`.
3. Edit `.env` for your local environment.
4. Run migrations.
5. Compile translations if `gettext` is available.
6. Create the runtime directories used for uploads and thumbnails.
7. Create the initial admin user.
8. Start the Django development server.
9. Start the background worker in a second terminal.

Commands:

```shell
cp .env.example .env
uv run manage.py migrate --run-syncdb
uv run manage.py compilemessages
uv run worker.py --init-files-dirs
uv run manage.py create_initial_user
uv run manage.py runserver
```

In another terminal:

```shell
uv run worker.py --daemon
```

Local configuration notes:

- `glifestream.settings` is the default local settings module.
- `.env` is loaded automatically when `GLIFESTREAM_LOAD_DOTENV=1` or unset.
- `glifestream/settings_local.py` is optional and is loaded automatically when `GLIFESTREAM_ENABLE_SETTINGS_LOCAL=1` or unset.
- `create_initial_user` creates `admin` / `admin` by default and forces a password change on first login.


Production Deployment and Hardening
===================================

Production defaults should come from environment variables, not from editing
committed settings files. Keep `GLIFESTREAM_VALIDATE_SETTINGS_SECRETS=1`
unless you are temporarily debugging startup.

Core production settings
------------------------

These settings matter most for a hardened deployment:

- `DEBUG` or `APP_DEBUG`
  Set to `0` in production. When `DEBUG=0`, secret validation is enforced and
  `DATABASE_NAME` must be configured.
- `SECRET_KEY` or `APP_SECRET_KEY`
  Set this to a long random value. Do not ship placeholder or development values.
- `ALLOWED_HOSTS`
  Set this to the hostnames served by your deployment, separated by commas.
- `BASE_URL`
  Set this to the externally visible site URL without a trailing slash.
  Use `https://...` when TLS is terminated by your reverse proxy or load balancer.
- `DATABASE_ENGINE`, `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`,
  `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_CHARSET`
  Configure these for your production database.
- `RUN_DIR`
  Runtime directory for DB files, templates, and generated static input.
  This directory must be persistent and writable if you rely on file-based runtime assets.
- `RUN_DIR_MEDIA` or `MEDIA_ROOT`
  Persistent media storage location for uploads and generated thumbnails.
- `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`
  Keep these enabled in production. `run.settings_docker` defaults both to `True`.
- `GLIFESTREAM_LOAD_DOTENV`
  Set to `0` when the process manager, orchestrator, or container runtime injects environment variables directly.
- `GLIFESTREAM_ENABLE_SETTINGS_LOCAL`
  Set to `0` for immutable or centrally managed deployments that should not load a local Python override file.
- `GLIFESTREAM_VALIDATE_SETTINGS_SECRETS`
  Leave enabled in production so placeholder secrets fail fast at startup.

Magic Link SSO settings
-----------------------

If you enable friends-only access through Magic Link SSO, also configure:

- `MAGICSSO_ENABLED=1`
- `MAGICSSO_SERVER_URL`
- `MAGICSSO_JWT_SECRET`
- `MAGICSSO_PREVIEW_SECRET`

Optional cookie and behavior settings are also supported, including:

- `MAGICSSO_COOKIE_NAME`
- `MAGICSSO_COOKIE_PATH`
- `MAGICSSO_COOKIE_DOMAIN`
- `MAGICSSO_COOKIE_MAX_AGE`
- `MAGICSSO_COOKIE_SAMESITE`
- `MAGICSSO_COOKIE_SECURE`
- `MAGICSSO_DIRECT_USE`
- `MAGICSSO_AUTH_EVERYWHERE`
- `MAGICSSO_REQUEST_TIMEOUT`

When `MAGICSSO_ENABLED=1` and secret validation is enabled, placeholder Magic
Link SSO secrets will fail startup when `DEBUG=0`.

Reverse proxy, TLS, and URL shape
---------------------------------

gLifestream is typically served behind a reverse proxy. Keep these rules in mind:

- Set `BASE_URL` to the public URL that browsers use to reach the site.
- Use an `https://` `BASE_URL` when TLS terminates before the Django process.
- In Docker, `run.settings_docker` derives path-prefix-aware URLs from `FORCE_SCRIPT_NAME` or `VIRTUAL_PATH`.
- When `VIRTUAL_PATH` is not `/`, Docker rewrites `STATIC_URL`, `MEDIA_URL`, `FAVICON`, and `LOGIN_URL` to include that prefix.
- The current Docker `HEALTHCHECK` only performs `curl -f http://localhost/`.
  It confirms that the container serves the root path successfully, but it does
  not verify deeper application readiness, worker health, database migrations,
  or third-party dependency availability.


Docker Deployment
=================

The repository ships a `docker-compose.yml`, a production-oriented `Dockerfile`,
and a `run.settings_docker` overlay.

What the container startup does
-------------------------------

The Docker entrypoint currently performs these steps on container start:

1. `python manage.py migrate --run-syncdb --fake-initial`
2. Load `glifestream/stream/fixtures/initial_data.json` if no `Service` rows exist
3. `python manage.py collectstatic --no-input`
4. `python worker.py --init-files-dirs`
5. `python manage.py create_initial_user`
6. Start Supervisor, which runs:
   - Gunicorn for the Django app
   - `python -u /app/worker.py --daemon` for background fetches and maintenance

Required environment values
---------------------------

At minimum, set these before starting a real deployment:

- `APP_SECRET_KEY`
- `APP_DEBUG=0`
- `ALLOWED_HOSTS`
- `BASE_URL`

Common Docker-specific values:

- `VIRTUAL_HOST`
- `VIRTUAL_PATH`
- `APP_PORT`
- `RUN_DIR`
- `RUN_DIR_MEDIA`

Persistent storage
------------------

The shipped Compose file persists:

- `/app/run` through `${RUN_DIR:-./run}`
- `/app/media` through `${RUN_DIR_MEDIA:-./run/media}`
- `/app/static` through the named volume `app_static`

Do not treat these as disposable in production. They contain runtime state,
uploaded media, generated thumbnails, and collected static files.

Example startup
---------------

Create or update your `.env` and then start the stack:

```shell
docker compose up -d --build
```

If you prefer the legacy command-line spelling, `docker-compose up -d --build`
uses the same repository file.

Operational notes
-----------------

- `run.settings_docker` defaults `DEBUG` to `False`.
- It switches sessions to `django.contrib.sessions.backends.cached_db`.
- It expects Memcached at `memcached:11211`.
- It extends `ALLOWED_HOSTS` with `VIRTUAL_HOST`, `localhost`, and `backend`.
- It keeps secure session and CSRF cookies enabled by default.
- The published image workflow builds multi-arch images for `linux/amd64` and `linux/arm64`.


Non-Docker Deployment
=====================

For non-container deployments, the repository still expects one web process and
one long-lived worker process.

Recommended shape
-----------------

- Reverse proxy: Nginx, Caddy, Apache, or equivalent
- Application server: Gunicorn serving `glifestream.wsgi:application`
- Background worker: `worker.py --daemon`
- Process supervision: systemd, Supervisor, s6, or equivalent

Suggested setup flow
--------------------

1. Export production environment variables.
2. Disable `.env` loading if your process manager already injects configuration:
   `GLIFESTREAM_LOAD_DOTENV=0`
3. Disable local Python overrides unless you intentionally rely on them:
   `GLIFESTREAM_ENABLE_SETTINGS_LOCAL=0`
4. Install dependencies:

```shell
uv sync
```

5. Run database migrations:

```shell
uv run manage.py migrate --run-syncdb
```

6. Compile translations if needed:

```shell
uv run manage.py compilemessages
```

7. Collect static files:

```shell
uv run manage.py collectstatic --no-input
```

8. Create runtime directories:

```shell
uv run worker.py --init-files-dirs
```

9. Create the initial admin account:

```shell
uv run manage.py create_initial_user
```

10. Start the web server and worker under supervision.

Example commands:

```shell
uv run gunicorn glifestream.wsgi:application --bind 0.0.0.0:8000 --workers 2
uv run worker.py --daemon
```

Non-Docker hardening notes
--------------------------

- Make sure `RUN_DIR`, `RUN_DIR_MEDIA`, and `STATIC_ROOT` live on persistent storage.
- If you keep the default file-based session backend, ensure session files are stored on persistent writable storage as well.
- Keep your reverse proxy responsible for TLS termination and static/media serving where appropriate.
- Re-run `collectstatic` during upgrades before restarting the web tier.
- Keep the worker process running continuously so scheduled imports and cleanup jobs continue to execute.


Production Checklist
====================

Before calling the deployment ready, verify:

- `APP_DEBUG=0` or `DEBUG=0`
- `APP_SECRET_KEY` or `SECRET_KEY` is changed from placeholder or development values
- `ALLOWED_HOSTS` matches the real served hostnames
- `BASE_URL` matches the external URL and uses `https://` when appropriate
- `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` are enabled
- Magic Link SSO secrets are changed from placeholders when `MAGICSSO_ENABLED=1`
- `RUN_DIR`, media storage, and static storage are persistent and writable
- database settings point to the intended production database
- migrations, `collectstatic`, and `worker.py --init-files-dirs` have been run successfully
- the web process is serving requests
- `worker.py --daemon` is running under supervision
- your upgrade procedure includes migrations, static collection, and controlled restarts

Receive Postings via E-mail
===========================

To enable posting by e-mail, create a secret mail alias that pipes messages to:

```text
gls.secret.address: "|/usr/local/django/glifestream/worker.py --email2post"
```


Testing
=======

Install development dependencies and the Playwright browser runtime:

```shell
uv sync --group dev
uv run python -m playwright install chromium
```

Run the test and code quality checks:

```shell
uv run pytest
uv run ruff check
uv run ty check
uv run mypy .
```

The browser E2E suite uses local mocked RSS and Atom feeds and exercises the
real `worker.py` ingestion path before asserting the rendered UI.

Visual regression testing builds on those same browser tests:

```shell
./scripts/vrt-docker.sh baseline
./scripts/vrt-docker.sh compare
```

To watch the E2E suite in a visible browser window:

```shell
GLS_E2E_HEADED=1 uv run pytest -m e2e
```

To slow the run down for observation:

```shell
GLS_E2E_HEADED=1 GLS_E2E_SLOWMO_MS=1000 uv run pytest -m e2e
```

To print each browser test name as it starts:

```shell
GLS_E2E_PRINT_TESTS=1 uv run pytest -m e2e
```
