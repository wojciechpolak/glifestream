# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries for versions up to and including 1.4 were reconstructed retroactively
from the Git history and are intentionally high-level.

## [Unreleased]

Covers everything since the `v1.4` tag (March 2021). This is a large span of
work, so only the significant changes are listed.

### Added

- Mastodon support, including OAuth 2.0 authentication, context cards with
  reply hydration, and video embeds.
- Bluesky/ATProto support, including native video embeds, reposts in the home
  timeline, context cards with reply hydration, and improved linkification and
  media expansion.
- PixelFed support.
- Dark Mode.
- Progressive Web App (PWA) support and Web Share integration.
- Docker-based deployment: Dockerfile, Compose setup, a separate Nginx service,
  and a GitHub Actions workflow publishing container images with build
  attestations.
- Worker daemon that replaces cron-driven fetches, with a retry-capable fetch
  scheduler and improved fetch failure handling.
- Service status tab in user settings.
- Fetch retries with backoff. A temporary failure is retried after one minute,
  doubling on each further failure up to the service's interval, and a longer
  `Retry-After` from the remote wins. A failure that retrying cannot fix waits
  at least a day. The status tab shows how many times in a row a service has
  failed. `FETCH_RETRY_BASE_SEC` and `FETCH_TERMINAL_DELAY_SEC` set the delays.
- A fetch timeout, `FETCH_JOB_TIMEOUT_SEC` (15 minutes by default). A service
  whose fetch hangs no longer stops the worker from fetching the others; it is
  recorded as timed out and retried with backoff.
- Magic Link SSO as the new backend for the "Friends Only" mode.
- `--uploads-list-orphans` (also `manage.py worker_cleanup`) reports uploaded
  files that no entry, `Media` row or template of the owner uses, such as the
  files of a deleted selfpost. It only lists them: gLifestream never moves or
  deletes an upload. The worker runs the report monthly and prints it to its
  log, with a warning when most uploads look unused, which points to a
  database that does not match `MEDIA_ROOT`.
- `docs/ARCHITECTURE.md`, describing the module layers, what each module owns,
  and how requests, imports and WebSub pushes move through the code. The layers
  are checked with `import-linter` (`uv run lint-imports`), in
  `./scripts/check` and in CI.
- Forced password change flow for initial admin accounts.
- `./scripts/bootstrap`, a one-command local setup. It installs the
  dependencies, writes a `.env` with random secrets, migrates the database,
  compiles translations, creates the media directories and the initial admin
  user. It is safe to run again and never overwrites an existing `.env`.
- Test infrastructure: pytest suite, Playwright E2E coverage (including OAuth
  and Bluesky service flows), optional visual regression testing, and coverage
  reporting.
- Static analysis and typing: type hints throughout, mypy, the `ty` checker, and
  Ruff.
- GitHub Actions CI (`pr-checks.yml`) and automated dependency updates via
  Dependabot.
- Support for additional image formats and a reworked thumbnail pipeline.
- Reblog filtering and an entry link shortcut in the admin view.

### Changed

- Migrated to Python 3 only; dropped the Six compatibility layer.
- Upgraded Django from 2.2 through 3.x, 4.2 and 5.x to Django 6.
- Switched the dependency manager to uv (previously Poetry and
  `requirements.txt`).
- Replaced uWSGI with Gunicorn.
- Rewrote the default layout and switched to Font Awesome; refreshed the default
  theme.
- Modernized the Django settings module.
- Renamed PubSubHubbub support to WebSub.
- Upgraded Markdown to v3.
- Refactored the stream index view and the settings views into smaller modules,
  and split `worker.py` into a package.
- Moved entry persistence out of the provider adapters into the new
  `glifestream.ingestion` package. Providers now yield `Candidate` and
  `NormalizedEntry` values. `ingest()` decides whether to create, update or skip
  each entry, stores it with its media in one transaction, and returns an
  `ImportResult`, which the fetcher logs after every fetch. Stored data is
  unchanged.
- Improved mobile stream interactions.
- Rewrote the page script in strict TypeScript without jQuery, built with
  esbuild from `frontend/`. Building needs Node.js; running the site does not.
  The lightbox is now PhotoSwipe 5, and the rich editor Quill 2, both bundled
  from npm.
- `user_alter_html` in `user-scripts.js` receives either the stream element or
  an array of the entries continuous reading added, no longer a jQuery set.
  Entries that continuous reading adds no longer run the scripts in their
  content.
- Pages send a Content Security Policy that allows scripts only from the
  static files. For now it only reports, in the browser console, what it would
  block. Set `CONTENT_SECURITY_POLICY=enforce` to block it, once an inline
  `<script>` in `user-scripts.js` or another template override carries
  `nonce="{{ csp_nonce }}"` and no template relies on inline event handler
  attributes. A later release will enforce it by default; `off` sends no
  policy.
- The templates hand the page script its data as JSON in `json_script`
  elements, and the script loads with `defer`. The inline `settings`,
  `stream_data` and `gettext_msg` globals, and the `i18n.html` template that
  defined `gettext_msg`, are gone; a user script can read
  `JSON.parse(document.getElementById('gls-config').textContent)` instead.
- The Docker container stops at the first startup step that fails, such as
  `migrate` or `collectstatic`, with that step's error. It used to start
  anyway and fail later, for example with a worker missing a database column.

### Deprecated

- `BaseService.resolve_entry()`. Providers should yield `Candidate` objects to
  `BaseService.ingest()` instead. The old method still works and emits a
  `DeprecationWarning`. A later release will remove it.

### Removed

- Legacy Sphinx search support.
- The bookmarklet.
- `requirements.txt` and the `workerpool` dependency.
- jQuery and fancyBox. A `user-scripts.js` that uses `$` needs its own copy of
  jQuery. A `PIPELINE` in `settings_local.py` that still lists
  `js/jquery.min.js`, `js/jquery.fancybox.min.js`, `quill/quill.min.js` or the
  fancyBox stylesheet stops `collectstatic` with `glifestream.E001`.

### Fixed

- The fetch status labels, the fetch messages and the year arrows of the
  archive calendar can be translated. The page script's messages are listed in
  one place, and a test checks the list against the script.
- `worker.py --init-files-dirs` no longer fails on a fresh checkout whose media
  directory does not exist yet.
- Re-importing an entry whose thumbnail is already registered no longer breaks
  the surrounding database transaction.
- Ingestion now logs a failed entry save instead of ignoring it.
- Two overlapping imports of one service, such as a WebSub push during a
  scheduled fetch, no longer lose an entry. The import that loses the insert
  race applies its data to the row the other one stored.
- Re-importing an entry no longer logs a database error for every thumbnail it
  already has.
- SQLite transactions run in `IMMEDIATE` mode with a 30 second busy timeout.
  Two transactions that read and then write, such as the worker claiming jobs
  while someone clicks "Run now", could fail one of them immediately with
  "database is locked".
- The fetch worker keeps running when one service's fetch fails. It used to
  re-raise that failure after the batch and exit, relying on a process manager
  to restart it.
- A second fetch worker now refuses to start while one is already running. It
  used to replace the running worker's wake socket and, on every cycle, mark
  that worker's fetches as interrupted and fetch the same services again. The
  worker holds a lock on `<WORKER_SOCKET>.lock` for as long as it runs.
- A failed Bluesky/ATProto fetch now shows up as failed. The provider used to
  swallow every error, from a rejected app password to a network outage, so
  the service status read "Fetch completed" and no retry was scheduled. Its
  client errors are now classified like HTTP errors: rejected credentials and
  unusable payloads wait for the long delay, timeouts, rate limits and server
  errors retry with backoff.
- A Bluesky/ATProto feed containing a post with an image gallery
  (`app.bsky.embed.gallery`) no longer fails to import. The AT Protocol SDK is
  upgraded to 0.0.72, which parses galleries and reads an embed type released
  after it without rejecting the whole feed. Gallery images render as
  thumbnails, like an image embed.
- A Mastodon or PixelFed fetch that gets a non-JSON response no longer records
  the service as checked.
- Resharing a post now registers its local thumbnails. The reshare used to
  register them before it saved the entry, so every registration failed and
  logged an error.
- Favoriting or resharing an entry with several remote images now stores a
  local copy of each. Only the last image in the entry used to be stored.
- `--thumbs-delete-orphans` no longer deletes a thumbnail that an import has
  just downloaded but not yet saved an entry for. Thumbnails newer than a day
  are left for the next run.
- `--thumbs-delete-orphans` no longer stops at a file that disappears while it
  runs, and it deletes a thumbnail from the directory it was found in rather
  than from the one its name implies.
- Numerous regressions in feed output, selfposts parsing, media permissions, and
  datetime handling (naive model datetimes are now normalized to UTC).

### Security

- Added CSRF protection across the application.
- Added outbound fetch guardrails to limit server-side request forgery risk.
- Regular dependency upgrades for `cryptography`, `urllib3`, `requests`, and
  `pyjwt`.

## [1.4] - 2021-03-30

### Added

- SCSS-based stylesheets.
- Fancybox v3 and jQuery 2.

### Changed

- Replaced the TinyMCE editor with Quill.
- Improved audio playback.

### Removed

- Facebook support.
- OpenID support.
- Obsolete service integrations and URL expanders.

## [1.3] - 2021-03-24

Ten years of incremental work between 2011 and 2021.

### Added

- Instagram support and Instagram URL expansion.
- Twitter entities support (photos).
- Python 3 compatibility via Six.
- Pillow-based image handling.
- CSS for mobile devices.
- `rel=canonical` links and the `STREAM_TITLE_SUFFIX` setting.
- hAtom author markup and conditional meta descriptions.
- Fancybox lightbox support.

### Changed

- Upgraded the codebase across Django 1.5, 1.7 and 1.11.
- Reorganized the project folder layout.
- Updated the Twitter API to v1.1 and the YouTube API to v3.
- Switched to the `requests` and `requests-oauthlib` libraries.
- Migrated search to SphinxQL.
- Moved to the `staticfiles` app with django-pipeline, and upgraded TinyMCE
  to 4.x.
- Applied PEP 8 formatting across the codebase.

### Removed

- Google Buzz support.
- The built-in translation feature.

### Fixed

- YouTube and Vimeo playback and feed handling.

## [1.2] - 2011-01-06

### Added

- Inline entry content editing with a TinyMCE editor.
- HTML5 placeholder support in forms.
- CSS sprites for the sharing icons.

### Changed

- Switched to Django 1.2+.
- Updated jQuery to 1.4.4 and started using larger YouTube thumbnails.
- Added `t.co` URL expansion.

## [1.0] - 2010-08-14

First tagged release.

### Added

- Core lifestream aggregation: a `Service`/`Entry`/`Media` data model joining
  external feeds and local `selfposts` into a single stream, with public and
  private (friends-only) visibility.
- Service integrations for RSS/Atom feeds, Twitter, Flickr, YouTube, Vimeo,
  Facebook and Google Buzz.
- Output as HTML, Atom and JSON (with JSONP), plus MediaRSS.
- Full-text search via Sphinx, with a simpler database-backed fallback.
- PubSubHubbub (push) support and feed autodiscovery.
- OAuth client support, OpenID login, and Facebook Connect for friends-only
  posts.
- Custom lists, draft posts, archive browsing and a "Continuous reading" mode.
- File uploads, image scaling and thumbnailing, and extensible oEmbed-based
  embeds.
- URL expansion filters for the common link shorteners and media hosts of the
  era.
- Posting by e-mail.
- OPML import/export.
- A user-facing settings page and the `worker.py` background task runner.
- Internationalization support.
