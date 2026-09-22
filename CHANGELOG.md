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
- Forced password change flow for initial admin accounts.
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

### Deprecated

- `BaseService.resolve_entry()`. Providers should yield `Candidate` objects to
  `BaseService.ingest()` instead. The old method still works and emits a
  `DeprecationWarning`. A later release will remove it.

### Removed

- Legacy Sphinx search support.
- The bookmarklet.
- `requirements.txt` and the `workerpool` dependency.

### Fixed

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
- Resharing a post now registers its local thumbnails. The reshare used to
  register them before it saved the entry, so every registration failed and
  logged an error.
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
