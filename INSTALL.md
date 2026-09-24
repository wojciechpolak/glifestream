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
- Node.js, the version in `.node-version`, to build the page script from `frontend/`.
  Only the build needs it: the site runs without Node, and the Docker image
  builds the script in a separate stage.
- `gettext` if you need to run `compilemessages`

Install dependencies with:

```shell
uv sync
npm ci
```


Local Development / First Run
=============================

One command takes a fresh checkout to a working instance:

```shell
./scripts/bootstrap
```

It runs `uv sync --group dev` and `npm ci`, builds the page script with
`npm run build`, creates `.env` from `.env.example` with random secrets, migrates the database, compiles translations when `gettext` is
installed, creates the media directories and the initial `admin` user, then
prints how to start the site and the worker. Every step is safe to repeat, so
you can run it again after pulling changes. It never overwrites an existing
`.env`.

To do the same by hand:

1. Change into the project directory.
2. Build the page script.
3. Copy `.env.example` to `.env`.
4. Edit `.env` for your local environment.
5. Run migrations.
6. Compile translations if `gettext` is available.
7. Create the runtime directories used for uploads and thumbnails.
8. Create the initial admin user.
9. Start the Django development server.
10. Start the background worker in a second terminal.

Commands:

```shell
npm ci
npm run build
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

The page script is TypeScript in `frontend/src/`, built into
`glifestream/static/js/dist/`, which is not in Git. After changing it, run
`npm run build` again, or keep this running while you work:

```shell
npm run watch
```

Without the built file, `runserver` and `collectstatic` stop with the system
check error `glifestream.E001`.

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
- `DATABASE_TIMEOUT_SEC`
  How long SQLite waits for another writer before giving up, in seconds.
  Defaults to `30`. gLifestream also runs SQLite transactions in `IMMEDIATE`
  mode, so a transaction that reads and then writes cannot fail another one
  with "database is locked". A deployment that defines `DATABASES` itself
  still gets both, unless it sets them to something else.
- `RUN_DIR`
  Runtime directory for DB files, templates, and generated static input.
  This directory must be persistent and writable if you rely on file-based runtime assets.
- `RUN_DIR_MEDIA` or `MEDIA_ROOT`
  Persistent media storage location for uploads and generated thumbnails.
- `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`
  Keep these enabled in production. `run.settings_docker` defaults both to `True`.
- `CONTENT_SECURITY_POLICY`
  `report-only` (the default), `enforce` or `off`. The policy runs scripts only
  from the static files, and from an inline script that carries the request's
  nonce: an override in `run/templates/`, such as `user-scripts.js`, writes
  `<script nonce="{{ csp_nonce }}">`. Inline event handler attributes do not
  run. `report-only` lets the browser report in its console what the policy
  would block without blocking it; once the console shows nothing, set
  `enforce`. A later release will make `enforce` the default. A `settings_local.py` that serves static
  files from another site sets `SECURE_CSP` again, from
  `glifestream.settings_csp.csp_settings()`.
- `GLIFESTREAM_LOAD_DOTENV`
  Set to `0` when the process manager, orchestrator, or container runtime injects environment variables directly.
- `GLIFESTREAM_ENABLE_SETTINGS_LOCAL`
  Set to `0` for immutable or centrally managed deployments that should not load a local Python override file.
- `GLIFESTREAM_VALIDATE_SETTINGS_SECRETS`
  Leave enabled in production so placeholder secrets fail fast at startup.

Background worker settings
--------------------------

The fetch worker (`./worker.py --daemon` or `manage.py run_worker`) reads:

- `WORKER_POOL_SIZE`
  How many services it fetches at the same time. Defaults to `4`.
- `FETCH_DEFAULT_INTERVAL_SEC`
  How often a service is fetched when it has no interval of its own, in
  seconds. Defaults to `7200`. A provider's own minimum wins when it is longer.
- `FETCH_RETRY_BASE_SEC`
  The first retry delay after a temporary failure such as a timeout or an HTTP
  5xx, in seconds. Defaults to `60`. Each further failure in a row doubles the
  delay, up to the service's interval. A longer `Retry-After` from the remote
  service wins.
- `FETCH_TERMINAL_DELAY_SEC`
  How long the worker waits after a failure that retrying cannot fix, such as
  an HTTP 404, rejected credentials or an unparsable feed, in seconds. Defaults
  to `86400`. The service's interval wins when it is longer. The next
  successful fetch returns the service to its normal interval.
- `FETCH_JOB_TIMEOUT_SEC`
  How long the worker waits for one service's fetch, in seconds. Defaults to
  `900`. After that it records the fetch as timed out, retries it like any
  other temporary failure, and goes on with the other services. Python cannot
  stop the stuck fetch, so it keeps running in the background, but it can no
  longer change the service's status or schedule.
- `FETCH_MEDIA_ALLOW_PRIVATE_ADDRESSES`
  Whether image downloads may reach loopback, private, link-local and other
  non-public addresses. Defaults to `0`. Image URLs come from the content of
  feeds and posts, so without this guard anyone who can put an image in a feed
  you follow could make the worker send requests into your network. Set it to
  `1` only if your sources serve images from your own network, for example a
  Mastodon instance on the LAN. Behind an outgoing HTTP proxy, the proxy
  decides which addresses can be reached.

Run one worker per installation. While it runs, the worker holds a lock on a
file beside its socket, `WORKER_SOCKET` plus `.lock`, and a second worker
started against the same socket exits with an error.

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

- An image never contains `glifestream/settings_local.py` or a `.env` file:
  `.dockerignore` keeps them out of the build, even from a working checkout.
  Configure a container through environment variables. For a Python override,
  put a module in the mounted `run/` that starts with
  `from run.settings_docker import *` and point `DJANGO_SETTINGS_MODULE` at it.
- `run.settings_docker` defaults `DEBUG` to `False`.
- It switches sessions to `django.contrib.sessions.backends.cached_db`.
- It expects Memcached at `memcached:11211`.
- It extends `ALLOWED_HOSTS` with `VIRTUAL_HOST`, `localhost`, and `backend`.
- It keeps secure session and CSRF cookies enabled by default.
- The `nginx` service serves `/media/` and `/static/` itself, from
  `run/nginx/templates/default.conf.template`. It sends media that a browser
  could run, such as HTML or SVG, as a download, and it rate-limits login
  attempts per client. If the stack sits behind another reverse proxy,
  uncomment the `set_real_ip_from` and `real_ip_header` lines in that template
  and set the proxy's address. Otherwise all clients share one login limit.
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
npm ci
```

5. Build the page script:

```shell
npm run build
```

6. Run database migrations:

```shell
uv run manage.py migrate --run-syncdb
```

7. Compile translations if needed:

```shell
uv run manage.py compilemessages
```

8. Collect static files:

```shell
uv run manage.py collectstatic --no-input
```

9. Create runtime directories:

```shell
uv run worker.py --init-files-dirs
```

10. Create the initial admin account:

```shell
uv run manage.py create_initial_user
```

11. Start the web server and worker under supervision.

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
- When the reverse proxy serves `/media/`, give it the headers gLifestream sends
  when it serves media itself. Otherwise an uploaded HTML or SVG file runs as
  your site. Send `X-Content-Type-Options: nosniff` for every file, and
  `Content-Disposition: attachment` for every type except images other than
  SVG, audio, video and PDF. `run/nginx/templates/default.conf.template` does
  this with a `map` on `$sent_http_content_type`.
- Rate-limit POST requests to `/login` and `/admin/login/` at the reverse
  proxy, because gLifestream itself does not slow down password guessing. The
  bundled nginx template allows each client 6 attempts a minute after a burst
  of 5, and answers `429` beyond that. If another proxy sits in front of the
  one that applies the limit, configure the real client address there
  (`set_real_ip_from` and `real_ip_header` in nginx). Otherwise all clients
  share one limit.
- Re-run `npm ci`, `npm run build` and then `collectstatic` during upgrades
  before restarting the web tier.
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
- The reverse proxy sends the media headers and rate-limits login attempts, as
  described under Non-Docker hardening notes
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

Install development dependencies, the frontend tooling and the Playwright
browser runtime:

```shell
uv sync --group dev
npm ci
uv run python -m playwright install chromium
```

The browser tests load the built page script, and the tests that render pages
with `DEBUG` off read the static files manifest. Build the script and collect
the static files before running them, and again after changing anything under
`frontend/`:

```shell
npm run build
uv run manage.py collectstatic --no-input
```

The E2E tests stop with a message when the built script is missing or older
than `frontend/src`.

Run every check in one pass, cheapest first:

```shell
./scripts/check
```

It runs ruff, oxlint, `lint-imports`, both TypeScript and Python type
checkers, Vitest, the frontend build and pytest. It does not stop at the
first failure, and prints a summary at the end. Formatting is left out,
because it rewrites files:

```shell
uv run ruff format
npm run format
```

To run the checks one at a time:

```shell
uv run pytest
uv run ruff check
uv run lint-imports
uv run ty check
uv run mypy .
npm test
npm run lint
npm run typecheck
```

`npm test` runs the Vitest unit tests next to the modules in `frontend/src/`.

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
