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
fetching | upgrades                   the fetch queue: claim, run, record, back off | upgrading old entries
stream.websub                         WebSub subscriptions, pushes and publishing
apis                                  provider adapters, one module per service
ingestion | filters                   storing entries | rewriting entry content
stream.media | gauth.gls_oauth*       thumbnails and uploads | OAuth clients
gauth.models                          OAuth tokens, user profiles
stream.models                         Service, Entry, Media, List, fetch state, upgrades
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
| Rewriting content (short links, video cards, music cards) | `filters` | Pure text in, text out, apart from thumbnail downloads. |
| The markup of a YouTube or Vimeo player | `filters/players.py` | Imports, posts, the editor's saves and the upgrades all store it. |
| Scheduling, retries and backoff | `fetching` | The only caller of `ServiceFactory` for scheduled fetches. |
| Telling WebSub hubs about new entries | `stream.websub.publish()` | Called by `fetching`: after an import, and for the requests `api_view` stores with `fetching.request_websub_publish()` after a share. Never by `ingestion` or `apis`. |
| Deleting old entries and orphaned thumbnails | `worker.maintenance` | Run on a schedule by the daemon or with `worker.py`. |
| Bringing old entries up to a provider's current markup | `upgrades` | Only when the owner approves each entry on the settings page. Every change can be reverted. |
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
`MEDIA_ROOT/upload/` and makes a thumbnail for each picture. Unless the share
was a draft, `api_view` then stores a `WebSubPublishRequest` and wakes the
daemon, which publishes to the WebSub hubs once for all the requests stored
so far. The owner does not wait for the hubs to answer.

A post's videos are players (`filters/players.py`): the video's thumbnail,
linked to its page, which the page script turns into the video. A video
address in the text becomes one (`expand.videolinks`), and `players.render()`
gives every player of the post today's markup and a thumbnail of its own,
so a player the editor inserted with the provider's thumbnail gets a local
copy.

`SelfpostsService.build()` makes the post without saving it, and `share()`
saves what it builds. `/api/preview` renders what `build()` makes, or an
edited entry as `/api/putcontent` would save it, through `stream-pure.html`
and saves nothing. The composer shows that article live under itself, where
the post will appear (`frontend/src/stream/preview.ts`), a moment after the
owner stops typing.

Editing an entry goes through `/api/editcontent` (the raw editor uses
`/api/getcontent` with `raw`) and `/api/putcontent`. The first gives the
composer the stored HTML with the thumbnail and upload addresses a browser
can load, its class (which only a post's may change) and its draft and
friends-only flags, which the composer sends back with it. The second turns the addresses back
into `[GLS-THUMBS]`/`[GLS-UPLOAD]` (`media.unset_media_urls()`). For a post
it also does what a share does to its videos and its music card, moves the
post to the class chosen (`selfposts.class_service()`), and gives it the
Media RSS of the videos it now shows (`media.mrss_with_videos()`).

The editor shows a music card as a block (`MusicCard` in
`frontend/src/editor/schema.ts`), which the composer's "Music track" fields
edit. It saves the card as the track it shows, and the server makes every
card of a post again from that (`music.render_cards()`): its saved cover,
the video's thumbnail for a missing one, and its search links. Without the
editor, the plain composer sends the fields, and the post gets the card
they make at its end.

## Upgrading old entries

An entry stores the HTML its provider rendered when it was imported. A later
change to the renderer reaches new imports only. `upgrades` brings the old
entries along, one at a time and only with the owner's approval:

1. Each provider's renderer is split into a pure `player_html()` and the code
   around it that picks and downloads the thumbnail. The import and the
   upgrade use the same functions.
2. An upgrader in `upgrades/<provider>.py` says an entry is legacy when its
   stored content, link or media differ from what `player_html()` gives now,
   or when its thumbnail is not in today's size and format. This check reads
   the database and the disk only, so the queue costs no requests. The next
   change to a renderer puts the affected entries in the queue without a new
   upgrader.
3. The settings page (`usettings.upgrade_settings`) shows the next entry
   rendered by `stream-pure.html` twice, as it is (A) and as the upgrade
   would leave it (B), with a diff of the source. Building B may download a
   thumbnail. Nothing else is written.
4. B goes to the form as a signed token holding the proposal and a hash of
   the entry. `upgrades.apply()` refuses the token once the entry has
   changed, so it stores exactly what the owner saw. It writes only
   `content`, `link` and `mblob`, never the dates, so the entry keeps its
   place in the stream. It keeps the old fields in an `EntryUpgrade` row.
5. `upgrades.revert()` puts the old fields back, unless the entry changed
   after the upgrade. While an upgrade stands, `--thumbs-delete-orphans`
   keeps the thumbnail it replaced.

An entry whose thumbnail is already current only changes its markup, and
its link and media where they are stale. It looks as it does now, so the
upgrader's `propose_offline()` builds its upgrade without a request, and
the owner may apply all such entries at once from a list with one sample
A/B. The list is signed with a hash of each entry; `apply_markup_only()`
leaves alone any entry that changed since. The upgrades share a `batch`,
which `revert_batch()` reverts together.

A skipped entry stays out of the queue until the owner offers the skipped
ones again. A reverted entry goes back into the queue.

Some upgrades need what only the owner knows. An upgrader may declare
`fields` and `guess()` their values from the entry; the review page then
shows a form above A/B, starts it from the guess, and builds B from what the
owner enters. Each upgrader's `markers` narrow the scan to the entries whose
content contains one of them.

The YouTube and Vimeo upgraders ask for the video, starting from the one
the entry shows, and link a search for the entry's title: a video the
provider no longer has gives way to another copy the owner finds.

The "Videos in posts" upgrader (`upgrades/post_videos.py`) does the same for
the players in posts, through `players.render()`. A post belongs to no
provider, so its video may become one of either. Its field changes the
first player; another one is changed in the editor.

The music upgrader asks for more: posts about a track that played on
thesixtyone.com, which is gone, or in a Spotify frame become a music card
(`filters/music.py`). The card shows the cover, the title and the artist;
the cover plays the YouTube video the owner names, and the card links to a
search for the track on Spotify, Apple Music, YouTube Music, Deezer, Tidal
and Bandcamp. Searches need no API and do not go stale. The composer makes
the same card for a new post from its "Music track" fields, through
`card_html()`, so a later change to the card queues the stored cards again.

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

The browser code lives in `frontend/src/`, outside the Python layers, and
uses the DOM directly, without jQuery. `npm run build` bundles it with esbuild
into `glifestream/static/js/dist/`, which is not in Git, for django-pipeline:

- `glifestream.js`, from `main.ts`, is the `main` bundle every page loads.
- `glifestream.css` holds the stylesheets the modules import, such as
  PhotoSwipe's for the lightbox; the `default` theme bundle puts it in front
  of the theme.
- `editor.js` and `editor.css`, from `editor.ts`, are the `editor` bundle:
  the rich editor (Tiptap, in `editor/`), which only the signed-in owner
  loads. It sets `window.create_gls_editor`, where the composer finds it; the
  composer sees only the `GlsEditor` interface, so the `main` bundle carries
  none of Tiptap. `editor/html.ts` keeps what it saves in the markup Quill,
  the editor before it, wrote, and `editor/schema.ts` reads that markup back.
  Its `Player` node shows a post's player as the stream does and saves it in
  the server's markup; a video address pasted on its own becomes one, and
  the toolbar's video button puts another video in the selected one.
  The toolbar's "HTML source" button shows the HTML the editor saves, to
  change in a textarea; it has no saving of its own, and the post publishes
  what the editor reads of it. "Raw Edit" on an entry instead saves its HTML
  as typed, past the editor.

PhotoSwipe and Tiptap are npm dependencies bundled in; nothing is vendored.
TypeScript 7 (`npm run typecheck`) only checks the types, in strict mode;
esbuild strips them, so the build does not depend on the checker.

```
main.ts          sets up the stream or the settings pages when ready
config.ts        reads the page data the templates write as JSON
stream/          entries, composer, sharing, media, maps, calendar, shortcuts
settings/        the service form and the fetch status of the settings pages
ui/              lightbox, effects, overlay, spinner, page controls,
                 pull to refresh
util/            ids, cookies, translations, DOM, events and scrolling
http.ts          fetch with the CSRF token, and the error report
```

- `util/dom.ts` has `h()`, which builds elements and inserts strings as text,
  and `listen()` and `delegate()`, which pass the handler its element. As
  with jQuery, a handler that returns false cancels the event.
- `ui/fx.ts` shows and hides with the Web Animations API, instantly when the
  reader prefers reduced motion. Each effect returns a promise.
- What a module keeps between events is an exported state object, such as
  `stream_state` or `composer`, not a closure.

- Templates hand the script its data as JSON, with `json_script`: the site
  config and the translated messages in `#gls-config` on every page, and the
  archive calendar in `#gls-stream-data` on stream pages. The tags that write
  them are in `stream/templatetags/gls_page.py`; `MESSAGES` there lists every
  message the script passes to `_()`. A deployment customizes the script
  through `user-scripts.js`, with the `window` globals declared in
  `frontend/src/globals.d.ts` and pinned by
  `glifestream/tests/e2e/test_js_extension_points.py`; that list is the
  contract a rewrite keeps.
- `frontend/src/api-types.ts` declares the JSON the script reads, and
  `glifestream/tests/test_frontend_contract.py` checks that the server sends
  it. Change the two together.
- The pages send a Content Security Policy (`settings_csp.py`, through
  Django's CSP middleware) that runs scripts only from the static files, so
  the markup has no inline script and no `on…` handler attribute: controls
  such as the logout link are marked with data attributes and bound by the
  script, and `glifestream/tests/test_csp.py` fails on inline code in a page.
  Both bundles load with `defer`. An inline script a deployment adds needs
  `nonce="{{ csp_nonce }}"`. The site only reports violations unless
  `CONTENT_SECURITY_POLICY=enforce`; the tests always enforce the policy, and
  the E2E page fixture fails any test during which the browser blocks
  something.
- Pipeline leaves a missing file out of a bundle without an error, so the
  system check `glifestream.E001` stops `runserver` and `collectstatic` when a
  bundle source, the built script included, cannot be found.
- The Playwright tests in `glifestream/tests/e2e/test_js_*.py` describe what
  the page does and sends, not how. Vitest tests sit next to the modules as
  `*.test.ts`. `GLS_E2E_JS_COVERAGE=1` reports which functions the browser
  tests never call, traced back to `frontend/src` through the source map. It
  reads the script `npm run build -- --no-minify` writes: a plain
  `npm run build` minifies it, for production.

## Adding things

- **A provider**: add a module under `apis/` that extends `BaseService`, yields
  `Candidate` objects and raises `FetchError` for remote failures. Register it
  in `apis/factory.py`, `apis/modules.py` and `stream.models.API_LIST`.
- **A side effect of a new entry** (a notification, an index update): call it
  from `fetching` or `api_view`, next to `websub.publish()` or
  `request_websub_publish()`. Do not call it from `ingestion` or a provider,
  which also run for WebSub pushes and would then fire it from inside an
  import.
- **An upgrade for another provider**: split its renderer into a pure
  `player_html()` (in `filters/players.py` for a video player) and the
  download around it, add an upgrader under
  `upgrades/` with its `markers`, `is_legacy()`, `propose()` and
  `propose_offline()` (and `fields` with `guess()` when the owner has to
  tell it something), and register it in `upgrades.service.UPGRADERS`.
- **A new top-level package**: add it to the layers in `pyproject.toml`, or
  `lint-imports` will not check it.
