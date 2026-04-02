"""
#  gLifestream Copyright (C) 2026 Wojciech Polak
#
#  This program is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License as published by the
#  Free Software Foundation; either version 3 of the License, or (at your
#  option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import sys
import threading
from collections.abc import Generator
from functools import partial
from http.server import (
    BaseHTTPRequestHandler,
    SimpleHTTPRequestHandler,
    ThreadingHTTPServer,
)
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from django.conf import settings as django_settings
from django.core.servers.basehttp import ThreadedWSGIServer, WSGIServer
from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper
from django.test.testcases import LiveServerThread
from django.core.management import call_command
from django.test.utils import modify_settings, setup_databases, teardown_databases
from pytest_django.fixtures import _get_databases_for_setup

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

from glifestream.stream.models import Service
from glifestream.tests.e2e.vrt import VisualRegressionSession

import worker as worker_module

FIXTURES_DIR = Path(__file__).parent / 'fixtures'
FEED_FIXTURES_DIR = FIXTURES_DIR / 'feeds'
MASTODON_FIXTURES_DIR = FIXTURES_DIR / 'mastodon'
ATPROTO_FIXTURES_DIR = FIXTURES_DIR / 'atproto'
ARTIFACTS_DIR = Path(__file__).parents[3] / 'test-results' / 'playwright'
VRT_ARTIFACTS_DIR = Path(__file__).parents[3] / 'test-results' / 'vrt'
MOCK_OAUTH2_CODE = 'gls-e2e-auth-code'
MOCK_OAUTH2_TOKEN = 'gls-e2e-access-token'
MOCK_AVATAR_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9pQnUnYAAAAASUVORK5CYII='
)
MOCK_ATPROTO_HANDLE = 'playwright.test'
MOCK_ATPROTO_DID = 'did:plc:playwrighttestaccount'


def _slugify_nodeid(nodeid: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '-', nodeid).strip('-')


def _env_flag(name: str) -> bool:
    value = os.environ.get(name, '')
    return value.lower() in {'1', 'true', 'yes', 'on'}


def _sqlite_connection_is_in_memory(conn: BaseDatabaseWrapper) -> bool:
    name = str(conn.settings_dict.get('NAME', ''))
    return name == ':memory:' or 'mode=memory' in name


@pytest.fixture(scope='session', autouse=True)
def clean_e2e_artifacts() -> Generator[None, None, None]:
    for path in (ARTIFACTS_DIR, VRT_ARTIFACTS_DIR):
        shutil.rmtree(path, ignore_errors=True)
    yield


class QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


class MockFeedServer:
    def __init__(
        self, root: Path, server: ThreadingHTTPServer, thread: threading.Thread
    ):
        self.root = root
        self.server = server
        self.thread = thread

    @property
    def base_url(self) -> str:
        host = cast(str, self.server.server_address[0])
        port = cast(int, self.server.server_address[1])
        return f'http://{host}:{port}'

    def publish_fixture(self, route: str, fixture_name: str) -> str:
        target = self.root / route.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FEED_FIXTURES_DIR / fixture_name, target)
        return self.url_for(route)

    def url_for(self, route: str) -> str:
        return f'{self.base_url}/{route.lstrip("/")}'

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def _with_mock_base_url(value: Any, base_url: str) -> Any:
    if isinstance(value, dict):
        return {key: _with_mock_base_url(item, base_url) for key, item in value.items()}
    if isinstance(value, list):
        return [_with_mock_base_url(item, base_url) for item in value]
    if isinstance(value, str):
        return value.replace('__MOCK_BASE_URL__', base_url)
    return value


def _make_mock_jwt(subject: str) -> str:
    def _encode(payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')

    header = _encode({'alg': 'none', 'typ': 'JWT'})
    payload = _encode({'sub': subject, 'exp': 4102444800, 'iat': 1893456000})
    signature = _encode({'sig': 'mock'})
    return f'{header}.{payload}.{signature}'


MOCK_ATPROTO_ACCESS_JWT = _make_mock_jwt('access')
MOCK_ATPROTO_REFRESH_JWT = _make_mock_jwt('refresh')


class MockOAuth2Server:
    def __init__(self, server: ThreadingHTTPServer, thread: threading.Thread):
        self.server = server
        self.thread = thread
        self.token_requests: list[dict[str, Any]] = []
        self.api_requests: list[dict[str, Any]] = []
        self.authorization_requests: list[dict[str, Any]] = []
        self._home_timeline: list[dict[str, Any]] = []

    @property
    def base_url(self) -> str:
        host = cast(str, self.server.server_address[0])
        port = cast(int, self.server.server_address[1])
        return f'http://{host}:{port}'

    def set_home_timeline(
        self, fixture_name_or_payload: str | list[dict[str, Any]]
    ) -> None:
        if isinstance(fixture_name_or_payload, str):
            payload = json.loads(
                (MASTODON_FIXTURES_DIR / fixture_name_or_payload).read_text(
                    encoding='utf-8'
                )
            )
        else:
            payload = fixture_name_or_payload
        self._home_timeline = cast(
            list[dict[str, Any]],
            _with_mock_base_url(payload, self.base_url),
        )

    def get_home_timeline(self) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            json.loads(json.dumps(self._home_timeline)),
        )

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class MockAtProtoServer:
    def __init__(self, server: ThreadingHTTPServer, thread: threading.Thread):
        self.server = server
        self.thread = thread
        self.session_requests: list[dict[str, Any]] = []
        self.profile_requests: list[dict[str, Any]] = []
        self.timeline_requests: list[dict[str, Any]] = []
        self._timeline: list[dict[str, Any]] = []

    @property
    def base_url(self) -> str:
        host = cast(str, self.server.server_address[0])
        port = cast(int, self.server.server_address[1])
        return f'http://{host}:{port}'

    def set_timeline(self, fixture_name_or_payload: str | list[dict[str, Any]]) -> None:
        if isinstance(fixture_name_or_payload, str):
            payload = json.loads(
                (ATPROTO_FIXTURES_DIR / fixture_name_or_payload).read_text(
                    encoding='utf-8'
                )
            )
        else:
            payload = fixture_name_or_payload
        self._timeline = cast(
            list[dict[str, Any]],
            _with_mock_base_url(payload, self.base_url),
        )

    def get_timeline(self) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            json.loads(json.dumps(self._timeline)),
        )

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class MockOAuth2Handler(BaseHTTPRequestHandler):
    server_version = 'MockOAuth2/1.0'

    @property
    def mock_server(self) -> MockOAuth2Server:
        return cast(MockOAuth2Server, getattr(self.server, 'mock_server'))

    def log_message(self, format: str, *args: object) -> None:
        return

    def _headers_dict(self) -> dict[str, str]:
        return {key: value for key, value in self.headers.items()}

    def _send_html(self, html: str, *, status: int = 200) -> None:
        data = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: Any, *, status: int = 200) -> None:
        data = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)

        if parsed.path == '/oauth/authorize':
            self.mock_server.authorization_requests.append(
                {
                    'path': parsed.path,
                    'query': query,
                    'headers': self._headers_dict(),
                }
            )
            approve_query = urlencode(
                {
                    'redirect_uri': query.get('redirect_uri', [''])[0],
                    'state': query.get('state', [''])[0],
                }
            )
            self._send_html(
                f"""
<!DOCTYPE html>
<html>
  <body>
    <main>
      <h1>Mock Mastodon Authorization</h1>
      <p>Authorize this test client.</p>
      <a id="authorize" href="/oauth/authorize/approve?{approve_query}">
        Authorize
      </a>
    </main>
  </body>
</html>
"""
            )
            return

        if parsed.path == '/oauth/authorize/approve':
            redirect_uri = query.get('redirect_uri', [''])[0]
            location = redirect_uri
            separator = '&' if '?' in redirect_uri else '?'
            location += separator + urlencode(
                {
                    'code': MOCK_OAUTH2_CODE,
                    'state': query.get('state', [''])[0],
                }
            )
            self._redirect(location)
            return

        if parsed.path == '/api/v1/timelines/home':
            self.mock_server.api_requests.append(
                {
                    'path': parsed.path,
                    'query': query,
                    'headers': self._headers_dict(),
                }
            )
            if self.headers.get('Authorization') != f'Bearer {MOCK_OAUTH2_TOKEN}':
                self._send_json({'error': 'unauthorized'}, status=401)
                return
            self._send_json(self.mock_server.get_home_timeline())
            return

        if parsed.path == '/media/avatar.png':
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(MOCK_AVATAR_PNG)))
            self.end_headers()
            self.wfile.write(MOCK_AVATAR_PNG)
            return

        self._send_json({'error': 'not_found'}, status=404)

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        content_length = int(self.headers.get('Content-Length', '0') or '0')
        body = self.rfile.read(content_length).decode('utf-8')
        form = parse_qs(body, keep_blank_values=True)

        if parsed.path == '/oauth/token':
            self.mock_server.token_requests.append(
                {
                    'path': parsed.path,
                    'body': body,
                    'form': form,
                    'headers': self._headers_dict(),
                }
            )
            if form.get('code', [''])[0] != MOCK_OAUTH2_CODE:
                self._send_json({'error': 'invalid_grant'}, status=400)
                return
            self._send_json(
                {
                    'access_token': MOCK_OAUTH2_TOKEN,
                    'token_type': 'Bearer',
                    'scope': 'read',
                }
            )
            return

        self._send_json({'error': 'not_found'}, status=404)


class MockAtProtoHandler(BaseHTTPRequestHandler):
    server_version = 'MockAtProto/1.0'

    @property
    def mock_server(self) -> MockAtProtoServer:
        return cast(MockAtProtoServer, getattr(self.server, 'mock_server'))

    def log_message(self, format: str, *args: object) -> None:
        return

    def _headers_dict(self) -> dict[str, str]:
        return {key: value for key, value in self.headers.items()}

    def _send_json(self, payload: Any, *, status: int = 200) -> None:
        data = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)

        if parsed.path == '/xrpc/app.bsky.actor.getProfile':
            self.mock_server.profile_requests.append(
                {
                    'path': parsed.path,
                    'query': query,
                    'headers': self._headers_dict(),
                }
            )
            self._send_json(
                {
                    '$type': 'app.bsky.actor.defs#profileViewDetailed',
                    'did': MOCK_ATPROTO_DID,
                    'handle': MOCK_ATPROTO_HANDLE,
                    'displayName': 'Playwright Bluesky',
                    'avatar': f'{self.mock_server.base_url}/avatar.png',
                    'createdAt': '2026-04-02T07:30:00.000Z',
                    'indexedAt': '2026-04-02T07:30:00.000Z',
                }
            )
            return

        if parsed.path == '/xrpc/app.bsky.feed.getTimeline':
            self.mock_server.timeline_requests.append(
                {
                    'path': parsed.path,
                    'query': query,
                    'headers': self._headers_dict(),
                }
            )
            if self.headers.get('Authorization') != f'Bearer {MOCK_ATPROTO_ACCESS_JWT}':
                self._send_json(
                    {'error': 'Unauthorized', 'message': 'Bad token'}, status=401
                )
                return
            self._send_json({'feed': self.mock_server.get_timeline()})
            return

        if parsed.path == '/avatar.png':
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(MOCK_AVATAR_PNG)))
            self.end_headers()
            self.wfile.write(MOCK_AVATAR_PNG)
            return

        self._send_json({'error': 'NotFound'}, status=404)

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        content_length = int(self.headers.get('Content-Length', '0') or '0')
        body = self.rfile.read(content_length).decode('utf-8')
        payload = json.loads(body) if body else {}

        if parsed.path == '/xrpc/com.atproto.server.createSession':
            self.mock_server.session_requests.append(
                {
                    'path': parsed.path,
                    'payload': payload,
                    'headers': self._headers_dict(),
                }
            )
            if (
                payload.get('identifier') != MOCK_ATPROTO_HANDLE
                or payload.get('password') != 'playwright-app-password'
            ):
                self._send_json(
                    {'error': 'AuthFailed', 'message': 'Invalid credentials'},
                    status=401,
                )
                return
            self._send_json(
                {
                    'accessJwt': MOCK_ATPROTO_ACCESS_JWT,
                    'refreshJwt': MOCK_ATPROTO_REFRESH_JWT,
                    'did': MOCK_ATPROTO_DID,
                    'handle': MOCK_ATPROTO_HANDLE,
                }
            )
            return

        self._send_json({'error': 'NotFound'}, status=404)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f'rep_{report.when}', report)


def pytest_runtest_logstart(nodeid: str, location: tuple[str, int, str]) -> None:
    del location
    if _env_flag('GLS_E2E_PRINT_TESTS'):
        print(f'[e2e] {nodeid}')


class SingleThreadLiveServerThread(LiveServerThread):
    # Avoid Django's threaded test server for SQLite-backed e2e runs.
    # Python 3.14 on Linux can segfault in _sqlite3 when many browser-driven
    # requests overlap across server threads.
    server_class = cast(type[ThreadedWSGIServer], WSGIServer)

    def _create_server(self, connections_override=None):
        del connections_override
        from django.test.testcases import QuietWSGIRequestHandler

        return self.server_class(
            (self.host, self.port),
            QuietWSGIRequestHandler,
            allow_reuse_address=False,
        )


class SingleThreadLiveServer:
    def __init__(self, addr: str, *, start: bool = True) -> None:
        from django.conf import settings
        from django.contrib.staticfiles.handlers import StaticFilesHandler
        from django.test.testcases import _StaticFilesHandler

        liveserver_kwargs: dict[str, Any] = {}
        connections_override = {}
        uses_sqlite = False

        for conn in connections.all():
            if conn.vendor == 'sqlite':
                uses_sqlite = True
                if _sqlite_connection_is_in_memory(conn):
                    connections_override[conn.alias] = conn

        liveserver_kwargs['connections_override'] = connections_override
        if 'django.contrib.staticfiles' in settings.INSTALLED_APPS:
            liveserver_kwargs['static_handler'] = StaticFilesHandler
        else:
            liveserver_kwargs['static_handler'] = _StaticFilesHandler

        try:
            host, port = addr.split(':')
        except ValueError:
            host = addr
        else:
            liveserver_kwargs['port'] = int(port)

        thread_class = SingleThreadLiveServerThread if uses_sqlite else LiveServerThread
        self.thread = thread_class(host, **liveserver_kwargs)
        self._live_server_modified_settings = modify_settings(
            ALLOWED_HOSTS={'append': host},
        )
        self.thread.daemon = True

        if start:
            self.start()

    def start(self) -> None:
        connections_override = self.thread.connections_override or {}
        for conn in connections_override.values():
            conn.inc_thread_sharing()

        self.thread.start()
        self.thread.is_ready.wait()

        if self.thread.error:
            error = self.thread.error
            self.stop()
            raise error

    def stop(self) -> None:
        self.thread.terminate()
        connections_override = self.thread.connections_override or {}
        for conn in connections_override.values():
            conn.dec_thread_sharing()

    @property
    def url(self) -> str:
        return f'http://{self.thread.host}:{self.thread.port}'

    def __str__(self) -> str:
        return self.url

    def __add__(self, other) -> str:
        return f'{self}{other}'

    def __repr__(self) -> str:
        return f'<LiveServer listening at {self.url}>'


@pytest.fixture(scope='session')
def django_db_setup(
    request: pytest.FixtureRequest,
    django_test_environment: None,
    django_db_blocker,
    django_db_use_migrations: bool,
    django_db_keepdb: bool,
    django_db_createdb: bool,
    django_db_modify_db_settings: None,
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[None, None, None]:
    db_dir = tmp_path_factory.mktemp('e2e-db')
    db_path = db_dir / 'glifestream-e2e.sqlite3'
    database_settings = cast(dict[str, Any], django_settings.DATABASES['default'])
    test_settings = cast(dict[str, Any], database_settings.get('TEST', {}))
    database_settings['NAME'] = str(db_path)
    test_settings['NAME'] = str(db_path)
    test_settings.setdefault('MIRROR', None)
    database_settings['TEST'] = test_settings
    django_settings.ALLOWED_HOSTS = list(
        dict.fromkeys(
            [*django_settings.ALLOWED_HOSTS, 'testserver', 'localhost', '127.0.0.1']
        )
    )

    setup_databases_args: dict[str, Any] = {}
    if django_db_keepdb and not django_db_createdb:
        setup_databases_args['keepdb'] = True

    aliases, serialized_aliases = _get_databases_for_setup(request.session.items)
    old_async_unsafe = os.environ.get('DJANGO_ALLOW_ASYNC_UNSAFE')
    os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

    with django_db_blocker.unblock():
        db_cfg = setup_databases(
            verbosity=request.config.option.verbose,
            interactive=False,
            aliases=cast(Any, aliases),
            serialized_aliases=cast(Any, serialized_aliases),
            **setup_databases_args,
        )

    yield

    if not django_db_keepdb:
        with django_db_blocker.unblock():
            try:
                teardown_databases(db_cfg, verbosity=request.config.option.verbose)
            except FileNotFoundError:
                pass

    if old_async_unsafe is None:
        del os.environ['DJANGO_ALLOW_ASYNC_UNSAFE']
    else:
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = old_async_unsafe


@pytest.fixture(scope='session')
def live_server(
    request: pytest.FixtureRequest,
) -> Generator[SingleThreadLiveServer, None, None]:
    addr = (
        request.config.getvalue('liveserver')
        or os.getenv('DJANGO_LIVE_TEST_SERVER_ADDRESS')
        or 'localhost'
    )

    server = SingleThreadLiveServer(addr)
    yield server
    server.stop()


@pytest.fixture(autouse=True)
def e2e_runtime_settings(settings, tmp_path: Path) -> Generator[Any, None, None]:
    media_root = tmp_path / 'media'
    upload_root = media_root / 'upload'
    thumbs_root = media_root / 'thumbs'
    session_root = tmp_path / 'sessions'
    static_root = tmp_path / 'static'
    old_insecure_transport = os.environ.get('OAUTHLIB_INSECURE_TRANSPORT')

    for path in (upload_root, session_root, static_root):
        path.mkdir(parents=True, exist_ok=True)
    for part in '0123456789abcdef':
        (thumbs_root / part).mkdir(parents=True, exist_ok=True)

    settings.ALLOWED_HOSTS = list(
        dict.fromkeys([*settings.ALLOWED_HOSTS, 'testserver', 'localhost', '127.0.0.1'])
    )
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        }
    }
    settings.MEDIA_ROOT = str(media_root)
    settings.MEDIA_URL = '/media/'
    settings.SESSION_ENGINE = 'django.contrib.sessions.backends.file'
    settings.SESSION_FILE_PATH = str(session_root)
    settings.STATIC_ROOT = str(static_root)
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    call_command('collectstatic', interactive=False, verbosity=0, clear=True)

    yield settings

    if old_insecure_transport is None:
        del os.environ['OAUTHLIB_INSECURE_TRANSPORT']
    else:
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = old_insecure_transport


@pytest.fixture
def seeded_e2e_state(transactional_db) -> None:
    call_command('create_initial_user', '--force')
    call_command('seed_e2e')


@pytest.fixture
def admin_credentials() -> dict[str, str]:
    return {
        'username': 'admin',
        'password': 'admin',
        'new_password': 'admin-pass-123',
    }


@pytest.fixture
def app_base_url(live_server, settings) -> str:
    host = urlsplit(live_server.url).hostname
    if host:
        settings.ALLOWED_HOSTS = list(dict.fromkeys([*settings.ALLOWED_HOSTS, host]))
    settings.BASE_URL = live_server.url
    return cast(str, live_server.url)


@pytest.fixture(scope='session')
def playwright_instance() -> Generator[Playwright, None, None]:
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture
def browser(playwright_instance: Playwright) -> Generator[Browser, None, None]:
    browser = playwright_instance.chromium.launch(
        headless=not _env_flag('GLS_E2E_HEADED'),
        slow_mo=int(os.environ.get('GLS_E2E_SLOWMO_MS', '0')),
    )
    yield browser
    browser.close()


@pytest.fixture
def page(
    browser: Browser, request: pytest.FixtureRequest
) -> Generator[Page, None, None]:
    node_slug = _slugify_nodeid(request.node.nodeid)
    test_artifacts = ARTIFACTS_DIR / node_slug
    test_artifacts.mkdir(parents=True, exist_ok=True)

    context: BrowserContext = browser.new_context(
        viewport={'width': 1440, 'height': 960}
    )
    if _env_flag('VRT'):
        context.add_init_script(
            """
            (() => {
                const disableEffects = () => {
                    if (window.jQuery && window.jQuery.fx) {
                        window.jQuery.fx.off = true;
                        return true;
                    }
                    return false;
                };

                if (disableEffects()) {
                    return;
                }

                let attempts = 0;
                const timer = window.setInterval(() => {
                    attempts += 1;
                    if (disableEffects() || attempts > 200) {
                        window.clearInterval(timer);
                    }
                }, 5);
            })();
            """
        )
    context.tracing.start(screenshots=True, snapshots=True)
    page = context.new_page()

    yield page

    failed = bool(
        getattr(request.node, 'rep_call', None) and request.node.rep_call.failed
    )
    if failed:
        page.screenshot(path=str(test_artifacts / 'failure.png'), full_page=True)
        context.tracing.stop(path=str(test_artifacts / 'trace.zip'))
    else:
        context.tracing.stop()
    context.close()


@pytest.fixture
def vrt(request: pytest.FixtureRequest) -> VisualRegressionSession:
    return VisualRegressionSession.from_request(request)


@pytest.fixture
def mock_feed_server(tmp_path: Path) -> Generator[MockFeedServer, None, None]:
    root = tmp_path / 'mock-feeds'
    root.mkdir(parents=True, exist_ok=True)

    handler = partial(QuietStaticHandler, directory=str(root))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    feed_server = MockFeedServer(root=root, server=server, thread=thread)
    yield feed_server
    feed_server.stop()


@pytest.fixture
def mock_oauth2_server() -> Generator[MockOAuth2Server, None, None]:
    server = ThreadingHTTPServer(('127.0.0.1', 0), MockOAuth2Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    oauth2_server = MockOAuth2Server(server=server, thread=thread)
    setattr(server, 'mock_server', oauth2_server)
    oauth2_server.set_home_timeline('home-initial.json')
    thread.start()

    yield oauth2_server

    oauth2_server.stop()


@pytest.fixture
def mock_atproto_server() -> Generator[MockAtProtoServer, None, None]:
    server = ThreadingHTTPServer(('127.0.0.1', 0), MockAtProtoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    atproto_server = MockAtProtoServer(server=server, thread=thread)
    setattr(server, 'mock_server', atproto_server)
    atproto_server.set_timeline('timeline-initial.json')
    thread.start()

    yield atproto_server

    atproto_server.stop()


@pytest.fixture
def create_webfeed_service():
    def _create(name: str, url: str, *, public: bool) -> Service:
        return Service.objects.create(
            api='webfeed',
            name=name,
            url=url,
            cls='feed',
            display='both',
            public=public,
            home=True,
            active=True,
        )

    return _create


@pytest.fixture
def configure_mock_atproto_client(monkeypatch):
    def _configure(base_url: str) -> None:
        from atproto import Client as RealClient

        def _client_factory(*args: Any, **kwargs: Any):
            if 'base_url' not in kwargs or kwargs['base_url'] is None:
                kwargs['base_url'] = base_url
            return RealClient(*args, **kwargs)

        monkeypatch.setattr('glifestream.apis.atproto.Client', _client_factory)

    return _configure


@pytest.fixture
def run_worker():
    def _run(*args: str) -> None:
        argv = ['worker.py', *args]
        original_argv = sys.argv[:]
        try:
            sys.argv = argv
            worker_module.run()
        finally:
            sys.argv = original_argv

    return _run


@pytest.fixture
def login_as_initial_admin(
    page: Page, app_base_url: str, seeded_e2e_state, admin_credentials
):
    def _login() -> None:
        page.goto(f'{app_base_url}/login')
        page.get_by_label('Username').fill(admin_credentials['username'])
        page.get_by_label('Password').fill(admin_credentials['password'])
        page.get_by_role('button', name='Log In').click()

    return _login


@pytest.fixture
def finish_forced_password_change(page: Page, admin_credentials):
    def _finish() -> None:
        page.get_by_label('New Password', exact=True).fill(
            admin_credentials['new_password']
        )
        page.get_by_label('Confirm New Password', exact=True).fill(
            admin_credentials['new_password']
        )
        page.get_by_role('button', name='Change Password').click()

    return _finish


@pytest.fixture
def ensure_admin_session(
    login_as_initial_admin,
    finish_forced_password_change,
    page: Page,
    app_base_url: str,
):
    def _ensure() -> None:
        login_as_initial_admin()
        if '/change-password' in page.url:
            finish_forced_password_change()
        if not page.url.startswith(app_base_url):
            page.goto(f'{app_base_url}/')

    return _ensure
