gLifestream -- INSTALL
Copyright (C) 2009-2026 Wojciech Polak

gLifestream requirements
========================

- Django -- a Python Web framework (https://www.djangoproject.com/)
- A database supported by Django (e.g. SQLite, MySQL, PostgreSQL).
- Universal Feed Parser (https://pypi.python.org/pypi/feedparser)

Install all necessary dependencies using [uv](https://docs.astral.sh/uv/).

```shell
$ uv sync
```

Installation instructions
=========================

1. Change the current working directory into the `glifestream` directory.
2. Copy `settings_sample.py` to `settings.py` and edit your local site
   configuration.
3. Run `uv run manage.py migrate --run-syncdb`
4. Run `uv run manage.py compilemessages` (if you have 'gettext' installed)
5. Run `./worker.py --init-files-dirs`

Make sure that `media/thumbs/*` and `media/upload` directories exist
and all have write permissions by your webserver.

Use `glifestream/worker.py` to automatically fetch external streams
(via cron), list available streams or remove old entries. See
`worker.py --help`.


The development/test server
---------------------------

Change the current working directory into the `glifestream` directory
and run the command `uv run manage.py runserver`. You will see
the following output:

    Performing system checks...

    System check identified no issues (0 silenced).
    October 18, 2023 - 21:52:38
    Django version 4.2.6, using settings 'glifestream.settings'
    Starting development server at http://127.0.0.1:8000/
    Quit the server with CONTROL-C.


Docker deployment
-----------------

```shell
# [adjust files in the `run` folder]
docker-compose up
```

Other deployments
-----------------

See https://docs.djangoproject.com/en/dev/howto/deployment/
for usual Django applications deployment.


The search functionality via Sphinx
===================================

To use the search functionality in GLS via Sphinx, you must add the
following configuration to your `/etc/sphinx/sphinx.conf` (replace the
`DATABASE_*` values with the proper ones from your `settings.py`):

```
source glifestream
{
   type         = mysql
   sql_host     = DATABASE_HOST
   sql_user     = DATABASE_USER
   sql_pass     = DATABASE_PASSWORD
   sql_db       = DATABASE_NAME
   sql_port     = 3306

   sql_query    = \
	SELECT stream_entry.id, stream_entry.title, stream_entry.content, \
	UNIX_TIMESTAMP(stream_entry.date_published) AS date_published, \
	stream_entry.friends_only, stream_service.public FROM stream_entry \
	INNER JOIN stream_service ON stream_entry.service_id=stream_service.id \
	WHERE stream_entry.active=1 AND stream_entry.draft=0

   sql_attr_timestamp = date_published
   sql_attr_bool      = public
   sql_attr_bool      = friends_only
}

index glifestream
{
   source       = glifestream
   path         = /var/lib/sphinx/glifestream
   docinfo      = extern
   charset_type = utf-8
   html_strip   = 1
}
```

Receive postings via e-mail
===========================

To allow for posts sent by e-mail, create a secret mail alias,
by extending `/etc/mail/aliases` file:

`
gls.secret.address: "|/usr/local/django/glifestream/worker.py --email2post"
`

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
uv run pytest -m e2e
uv run ruff check .
uv run mypy .
```

The browser E2E suite uses local mocked RSS/Atom feeds and runs the real
`worker.py` ingestion path before asserting the rendered UI.

To watch the E2E suite in a visible browser window, run it in headed mode:

```shell
GLS_E2E_HEADED=1 uv run pytest -m e2e
```

If you want the run to slow down so the navigation is easier to follow:

```shell
GLS_E2E_HEADED=1 GLS_E2E_SLOWMO_MS=1000 uv run pytest -m e2e
```

If you also want each browser test name printed as it starts:

```shell
GLS_E2E_PRINT_TESTS=1 uv run pytest -m e2e
```
