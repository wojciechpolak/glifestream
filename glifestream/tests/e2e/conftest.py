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

import os
import re
import shutil
import sys
import threading
from collections.abc import Generator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import pytest
from django.conf import settings as django_settings
from django.core.management import call_command
from django.test.utils import setup_databases, teardown_databases
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

FIXTURES_DIR = Path(__file__).parent / 'fixtures' / 'feeds'
ARTIFACTS_DIR = Path(__file__).parents[3] / 'test-results' / 'playwright'
VRT_ARTIFACTS_DIR = Path(__file__).parents[3] / 'test-results' / 'vrt'


def _slugify_nodeid(nodeid: str) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '-', nodeid).strip('-')


def _env_flag(name: str) -> bool:
    value = os.environ.get(name, '')
    return value.lower() in {'1', 'true', 'yes', 'on'}


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
        shutil.copyfile(FIXTURES_DIR / fixture_name, target)
        return self.url_for(route)

    def url_for(self, route: str) -> str:
        return f'{self.base_url}/{route.lstrip("/")}'

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f'rep_{report.when}', report)


def pytest_runtest_logstart(nodeid: str, location: tuple[str, int, str]) -> None:
    del location
    if _env_flag('GLS_E2E_PRINT_TESTS'):
        print(f'[e2e] {nodeid}')


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


@pytest.fixture(autouse=True)
def e2e_runtime_settings(settings, tmp_path: Path):
    media_root = tmp_path / 'media'
    upload_root = media_root / 'upload'
    thumbs_root = media_root / 'thumbs'
    session_root = tmp_path / 'sessions'
    static_root = tmp_path / 'static'

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
    call_command('collectstatic', interactive=False, verbosity=0, clear=True)

    return settings


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
