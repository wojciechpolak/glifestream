Contributing to gLifestream
===========================

gLifestream is a self-hosted Django application with a strict TypeScript
page script. This guide covers setting up a checkout, running the checks,
the conventions the tests follow, and what a change needs before it is
merged. [INSTALL](INSTALL.md) is the reference for deployment and for every
environment variable; [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) explains
how the code is laid out and which module owns what.


Setting up
----------

Install the tools under [Requirements](INSTALL.md#requirements), then set
up the checkout as
[Local Development / First Run](INSTALL.md#local-development--first-run)
describes:

```shell
./scripts/bootstrap
```

Run it again after a pull to bring the checkout up to date.

The test suite needs two more things the bootstrap leaves out, the Playwright
browser and the static files manifest:

```shell
uv run python -m playwright install chromium
uv run manage.py collectstatic --no-input
```

While you work on `frontend/src/`, keep `npm run watch` running, so the page
loads the script you just changed.


Running the checks
------------------

```shell
./scripts/check
```

This is the same set CI runs on every pull request: ruff, oxlint,
`lint-imports`, tsc, ty, mypy, Vitest, the frontend build and pytest,
cheapest first. It does not stop at the first failure, so one run shows
every problem, and it ends with a pass/fail table.

It leaves formatting out, because the formatters rewrite files. Run them
yourself before you commit:

```shell
uv run ruff format
npm run format
```

To narrow a failure down, run one tool at a time:

```shell
uv run ruff check
uv run lint-imports
uv run ty check
uv run mypy .
uv run pytest
npm run lint
npm run typecheck
npm test
```

or one test, or only the browser tests:

```shell
uv run pytest glifestream/tests/test_ingestion.py::test_name
uv run pytest -m e2e
```

The browser tests start a live server and run the real `worker.py` import
against local copies of the remote feeds before they check the page. To
watch them:

```shell
GLS_E2E_HEADED=1 uv run pytest -m e2e
GLS_E2E_HEADED=1 GLS_E2E_SLOWMO_MS=1000 uv run pytest -m e2e
GLS_E2E_PRINT_TESTS=1 uv run pytest -m e2e
```

The first opens a visible browser window, the second also slows each step
down, and the third prints each test's name as it starts.
`GLS_E2E_JS_COVERAGE=1` reports the page-script functions no browser test
calls; it needs a readable build, `npm run build -- --no-minify`.

Two things make tests fail for reasons outside your change:

- The browser tests load the built page script and stop with a message when
  it is missing or older than `frontend/src`. Run `npm run build`.
- Tests that render pages with `DEBUG` off read the static files manifest.
  After changing a pipeline bundle, run `collectstatic` again.


Where tests go
--------------

Python tests live in `glifestream/tests/`, one `test_<module>.py` per area
(`test_apis_mastodon.py`, `test_utils_html.py`). Vitest tests sit next to the
TypeScript module they cover, as `frontend/src/<module>.test.ts`.

**Shared fixtures.** `glifestream/tests/conftest.py` provides `user` and a
public feed `service`. It also enforces the Content Security Policy in every
test, whatever the default is, so a page that relies on an inline script
fails the test rather than a deployment.

**Remote services.** Unit tests never reach the network. Patch the module's
`httpclient` (or the parser it calls) with `unittest.mock.patch`, as the
`test_apis_*.py` files do, and build payloads inline. Browser tests run the
real worker against a local HTTP server that serves the canned responses in
`glifestream/tests/e2e/fixtures/` (`feeds/`, `mastodon/`, `atproto/`). Add a
file there when a browser test needs a new remote response.

**Browser test data.** The E2E suite seeds its database with
`manage.py seed_e2e`, which is idempotent. Extend it rather than creating
rows in a single test when several tests need the same data. Mark every
browser test `@pytest.mark.e2e`. The page fixture fails a test on anything
the browser's CSP blocks.

**Golden import data.** `test_ingestion_bc.py` compares the `Entry` and
`Media` rows each provider stores against `tests/golden/ingestion_bc.json`.
A diff there means imports now store different data. Re-record the file only
when that is the intended result of your change, and say so in the commit:

```shell
GLS_RECORD_GOLDEN=1 uv run pytest glifestream/tests/test_ingestion_bc.py
```

**The page script's contract.** `frontend/src/api-types.ts` and
`test_frontend_contract.py` describe the JSON the page script reads. Change
them together. The Playwright tests in `tests/e2e/test_js_*.py` pin what the
page does from the reader's side; if you change one of them while
rewriting the code under it, explain why in the commit.

**App fixtures.** `glifestream/stream/fixtures/initial_data.json` (the
starting services) and `welcome.json` (the welcome entry) are the starting
data `manage.py load_initial_data` puts into an empty database, for Docker and
`./scripts/bootstrap` alike. They are not test data.

**Visual regression.** Screenshot baselines are committed under
`.visual-regression/` and are compared in Docker, so they do not depend on
the fonts of your machine:

```shell
./scripts/vrt-docker.sh compare
./scripts/vrt-docker.sh baseline
```

Record a new baseline only for an intended visual change, and commit it with
that change.

**README screenshots.** `docs/screenshots/stream-light.webp` and
`stream-dark.webp` show the home page of a fresh installation with the
welcome entry. Take them again after a visible change to that page:

```shell
./scripts/screenshots
```

It serves a throwaway instance from a temporary directory, so your own `.env`
and data stay out of the pictures. It needs the network, for the video
thumbnail from YouTube, and Playwright's Chromium.


Conventions
-----------

**Module layers.** `lint-imports` enforces the layers declared under
`[tool.importlinter]` in `pyproject.toml`: a module imports only from layers
below its own. When a contract breaks, move the code to the layer that owns
it; do not add an exception. A new top-level package goes into the layers
too, or nothing checks it.

**Providers.** A provider only maps a remote payload. It yields `Candidate`
objects to `BaseService.ingest()` and never calls `Entry.save()`; the
`ingestion` package decides what to write. Adding one means registering it
in `apis/factory.py`, `apis/modules.py` and `stream.models.API_LIST`.
[ARCHITECTURE](docs/ARCHITECTURE.md#adding-things) covers this and where a
new side effect of an import belongs.

**Settings.** Every setting is read from the environment in
`glifestream/settings.py`. A new one needs a default that works for a
development checkout and an entry in the environment reference in
`INSTALL.md`. Add it to `.env.example` only if a development checkout has to
set it.

**Templates and the page script.** Pages send a Content Security Policy, so
a template has no inline `<script>` and no `on…` attribute;
`tests/test_csp.py` checks this. Templates pass data to the page script as
JSON through `stream/templatetags/gls_page.py`. The page script is strict
TypeScript on the plain DOM: no jQuery, and a new npm dependency needs a
reason.

**Style.** ruff and oxfmt decide the formatting; Python uses single quotes.
Comments explain why the code does something, not what it does.

**Translations.** User-facing strings go through Django's `gettext`. The
Polish catalogue is in `locale/pl/`. Update it with `makemessages` when you
add strings, if you can; otherwise mention the new strings in the pull
request.


Commits and pull requests
-------------------------

Keep a pull request to one change, and make sure `./scripts/check` passes
and both formatters have run before you ask for a review. CI runs the same
checks.

Commit subjects follow [Conventional Commits](https://www.conventionalcommits.org/)
in the imperative and describe the effect, not the edit:

```text
fix: keep a refused fetch shown as failed on the status page
feat: share to Mastodon, Bluesky and X from the share box
refactor: move entry persistence into an ingestion service
```

The types in use are `feat`, `fix`, `refactor`, `test`, `docs`, `build`,
`ci` and `chore`. Use the body for anything a reviewer cannot see in the
diff: the reason for the change, a golden file or baseline you re-recorded,
a behaviour a `test_js_*.py` test no longer pins.

A change someone running gLifestream would notice (a feature, a fix, a new
setting, a migration, a step to take when upgrading) gets an entry under
`[Unreleased]` in [CHANGELOG](CHANGELOG.md), in the same pull request.

A review looks for:

- a test that fails without the change, for every fix
- tests for new behaviour, at the lowest level that can show it: a unit test
  where one will do, a browser test only for what happens in the page
- no new calls to the network from tests
- migrations for model changes, which work on SQLite and do not depend on one
  database backend
- docs updated where the change makes them wrong: `INSTALL.md`,
  `docs/ARCHITECTURE.md`, `CHANGELOG.md`


License
-------

gLifestream is licensed under the GNU General Public License, version 3 or
later. By contributing, you agree that your contribution is licensed under
the same terms.
