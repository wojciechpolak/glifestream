# Architecture

gLifestream is one Django project. There is no separate service or message
broker: the web process and the fetch worker share the same code and database.
This page shows how a request, an import and a WebSub push move through the
code, which module owns each step, and which modules may import which.

## Layers

The code is split into layers. A module may import from the layers below its
own, never from one above. Modules on the same line sit side by side and may
not import each other. `lint-imports` checks this on every `./scripts/check`
and CI run. The contract is `[tool.importlinter]` in `pyproject.toml`.

```
urls                                  URL routing
stream.management                     manage.py commands
worker | usettings | stream.views     worker CLI and daemon, settings pages, view entry points
stream.api_view                       /api/<cmd>: share, reshare, favorite, hide
stream.index_view                     stream, archive, list and entry pages
stream.templatetags | gauth.views     template filters | login, logout, password change
fetching                              the fetch queue: claim, run, record, back off
stream.websub                         WebSub subscriptions, pushes and publishing
apis                                  provider adapters, one module per service
ingestion | filters                   storing entries | rewriting entry content
stream.media | gauth.gls_oauth*       thumbnails and uploads | OAuth clients
gauth.models                          OAuth tokens, user profiles
stream.models                         Service, Entry, Media, List, fetch state
utils                                 HTTP, HTML, time and slug helpers
```

Modules missing from the diagram, such as `stream.admin`, `gauth.middleware`
and the settings modules, are outside the contract. They still cannot give a
lower layer a way around it: `lint-imports` follows indirect imports too.

## Who owns what

| Operation | Owner | Notes |
|---|---|---|
| Talking to a remote service | `apis/<provider>.py` | Maps a payload to `Candidate` objects. Never saves an `Entry`. |
| Choosing a provider for a service | `apis/factory.py`, `apis/modules.py` | Adding a provider means updating both dicts. |
| Values a service's `api` column may hold | `stream.models.API_LIST` | The model owns its own choices. |
| Deciding whether to write an entry | `ingestion.ingest()` | Applies the protected flag, freshness and `force_overwrite`. |
| Saving an entry and its media rows | `ingestion.service` | One transaction per entry. |
| Downloading and storing thumbnails | `stream.media.save_image()` | Called by providers and filters while they build content. |
| Registering thumbnails as `Media` rows | `stream.media.extract_and_register()` | Called by `ingestion` and by selfposts. |
| Rewriting content (short links, video cards) | `filters` | Pure text in, text out, apart from thumbnail downloads. |
| Scheduling, retries and backoff | `fetching` | The only caller of `ServiceFactory` for scheduled fetches. |
| Telling WebSub hubs about new entries | `stream.websub.publish()` | Called by `fetching` after an import and by `api_view` after a share. Never by `ingestion` or `apis`. |
| Deleting old entries and orphaned thumbnails | `worker.maintenance` | Run on a schedule by the daemon or with `worker.py`. |
| Settings | `glifestream/settings.py` | Read from the environment; see `INSTALL.md`. |

## A page request

1. `urls` routes the request to `stream.views`, a thin layer that hands it
   to `index_view` or `api_view`.
2. `gauth.request_auth` decides who the visitor is: the owner, a friend
   signed in through Magic Link SSO, or an anonymous visitor.
3. `index_view` builds the entry query from the URL: context (all, public,
   favorites, list), date and search. Then it paginates the result and renders
   the HTML, Atom or JSON template.
4. Templates render entry content through `stream.templatetags.gls_filters`.
   `gls_content` gives the provider module a chance to reformat its own
   entries, and replaces the stored `[GLS-THUMBS]` and `[GLS-UPLOAD]`
   placeholders with URLs under `MEDIA_URL`.

## An import

```
worker daemon ─▶ fetching.claim_runnable_jobs ─▶ fetching.run_service_fetch
                                                        │
                        ServiceFactory ─▶ provider.run()│
                                              │         │
                          Candidate(guid, freshness, build)
                                              │         │
                          ingestion.ingest ───┘         │
                            build() ─▶ NormalizedEntry  │
                            save Entry + Media rows     │
                                                        ▼
                                    record success or failure, schedule next
                                    websub.publish() if public entries changed
```

1. The daemon (`worker/daemon.py`) wakes up when a fetch is due, or when
   someone clicks "Run now" and `enqueue_manual_fetch` writes to its socket.
   Only one daemon runs per installation. A second one refuses to start.
2. `claim_runnable_jobs` marks due services as running in one transaction.
   Each claimed job runs in a thread pool, limited by `FETCH_JOB_TIMEOUT_SEC`.
3. The provider fetches from the remote through `utils.httpclient`. HTTP
   errors, timeouts and unusable payloads come back as a `FetchError` with a
   category.
4. The provider yields one `Candidate` per remote item. `ingest()` calls
   `build()` only for items it will write, so a skipped item downloads no
   thumbnails.
5. `fetching` records the outcome in `ServiceFetchState`. It schedules the
   next fetch after the interval, after a backoff delay for a failure that can
   be retried, or after the long delay for a failure that cannot. If the
   newest public entry changed, it publishes to the WebSub hubs.

## A WebSub push

A webfeed service can subscribe to its feed's hub (`worker.py --websub`). The
hub then posts new content to `/websub/<id>`. `stream.websub.accept_payload`
checks the signature and hands the payload to the provider's `run()`, which
goes through `ingest()` as above but outside the fetch queue.

## Selfposts and shares

The share form posts to `/api/share`, and "reshare" on an entry posts to
`/api/reshare`. `api_view` passes both to `apis.selfposts`. Unlike the other
providers, it saves its entry itself: the owner wrote it, so there is nothing
to fetch and nothing for `ingest()` to compare. Selfposts stores uploads under
`MEDIA_ROOT/upload/` and makes a thumbnail for each picture. `api_view` then
publishes to the WebSub hubs, unless the share was a draft.

## Media on disk

- `MEDIA_ROOT/thumbs/<first hex digit>/<sha1>.<ext>` holds thumbnails. The
  file name is the SHA-1 of the source URL, so every entry that shows the
  same image shares one file. Content refers to a thumbnail as
  `[GLS-THUMBS]/<sha1>.<ext>`.
- `MEDIA_ROOT/upload/YYYY/MM/DD/<random>/<file name>` holds selfpost uploads,
  referred to as `[GLS-UPLOAD]/...`. The random directory makes the path
  impossible to guess, so the file of a draft or friends-only entry cannot be
  fetched by trying likely names. Uploads from before this change sit directly
  under the date. An upload is the only copy of a file the owner posted.
- A thumbnail no entry refers to is an orphan. `--thumbs-delete-orphans`
  removes orphans older than a day. Anything newer may belong to an import
  still in progress. `delete_thumb_files()` refuses any path outside
  `thumbs/`.
- Uploads are never deleted or moved by gLifestream. Deleting an entry leaves
  its uploaded files on disk. `--uploads-list-orphans` only reports the ones
  that no `Media` row, entry or owner template mentions. Removing them is up
  to the owner.

## The page script

The browser code lives in `frontend/src/`, outside the Python layers.
`npm run build` bundles `main.ts` with esbuild into
`glifestream/static/js/dist/glifestream.js`, which is not in Git, and
django-pipeline appends it to jQuery and fancyBox in its `main` bundle.
TypeScript 7 (`npm run typecheck`) only checks the types, in strict mode;
esbuild strips them, so the build does not depend on the checker.

```
main.ts          sets up the stream or the settings pages when ready
stream/          entries, composer, sharing, media, maps, calendar, shortcuts
settings/        the service form and the fetch status of the settings pages
ui/              lightbox, overlay, spinner, pull to refresh
util/            ids, cookies, translations, DOM and scrolling helpers
http.ts          CSRF header and error report for every jQuery request
```

The modules still use jQuery, which pipeline loads first, and handlers still
read their element from `this`. What a module keeps between events is an
exported state object, such as `stream_state` or `composer`, not a closure.

- Templates hand the script its data in the globals `settings`, `stream_data`
  and `gettext_msg`, declared in `frontend/src/globals.d.ts`. A deployment
  customizes it through `user-scripts.js`, with the `window` globals declared
  there and pinned by `glifestream/tests/e2e/test_js_extension_points.py`;
  that list is the contract a rewrite keeps.
- `frontend/src/api-types.ts` declares the JSON the script reads, and
  `glifestream/tests/test_frontend_contract.py` checks that the views send
  it. Change the two together.
- Pipeline leaves a missing file out of a bundle without an error, so the
  system check `glifestream.E001` stops `runserver` and `collectstatic` when a
  bundle source, the built script included, cannot be found.
- The Playwright tests in `glifestream/tests/e2e/test_js_*.py` describe what
  the page does and sends, not how. Vitest tests sit next to the modules as
  `*.test.ts`. `GLS_E2E_JS_COVERAGE=1` reports which functions the browser
  tests never call, traced back to `frontend/src` through the source map.

## Adding things

- **A provider**: add a module under `apis/` that extends `BaseService`, yields
  `Candidate` objects and raises `FetchError` for remote failures. Register it
  in `apis/factory.py`, `apis/modules.py` and `stream.models.API_LIST`.
- **A side effect of a new entry** (a notification, an index update): call it
  from `fetching` or `api_view`, next to `websub.publish()`. Do not call it
  from `ingestion` or a provider, which also run for WebSub pushes and
  would then fire it from inside an import.
- **A new top-level package**: add it to the layers in `pyproject.toml`, or
  `lint-imports` will not check it.
