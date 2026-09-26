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

Characterization tests for the settings pages behaviour of glifestream.js.

Like test_js_stream.py, they pin what the user sees and what reaches the
server, so they must keep passing unchanged while the script is rewritten.

In a full pytest run the live server shares the test thread's database
connection, so the test thread must not query while the page has a request in
flight. Rows are created before the page loads, database checks run only after
the page shows the response, and the fetch endpoints, which would otherwise
start the worker, are stubbed. Status page tests install Playwright's clock,
so the status polling runs only when a test advances it and cannot hit the
server during teardown.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs

import pytest
from playwright.sync_api import Dialog, Page, Request, Route, expect

from glifestream.stream.models import List, Service, WebSub

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def _form(request: Request) -> dict[str, list[str]]:
    return parse_qs(request.post_data or '', keep_blank_values=True)


def _is_service_api(method: str) -> Any:
    def _match(request: Request) -> bool:
        return (
            request.method == 'POST'
            and request.url.endswith('/settings/api/service')
            and _form(request).get('method') == [method]
        )

    return _match


def _json(route: Route, body: Any, status: int = 200) -> None:
    route.fulfill(status=status, content_type='application/json', body=json.dumps(body))


def _record_dialogs(page: Page, *, accept: bool) -> list[str]:
    messages: list[str] = []

    def _handle(dialog: Dialog) -> None:
        messages.append(dialog.message)
        if accept:
            dialog.accept()
        else:
            dialog.dismiss()

    page.on('dialog', _handle)
    return messages


def _row(page: Page, field: str) -> Any:
    return page.locator('#service-form .form-row', has=page.locator(f'#{field}'))


# --- Service form -----------------------------------------------------------


def test_add_service_form_toggles_dependent_fields(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/settings/services')
    form = page.locator('#service-form')

    with page.expect_request(_is_service_api('get')) as request_info:
        page.locator('#add-service a.mastodon').click()
    assert _form(request_info.value) == {'method': ['get'], 'api': ['mastodon']}
    expect(form).to_be_visible()
    expect(page.locator('#name')).to_be_focused()
    expect(form.locator('input[type=hidden][name=api]')).to_have_value('mastodon')
    expect(form.locator('input[type=hidden][name=id]')).to_have_count(0)
    expect(page.locator('#home')).to_be_checked()
    expect(page.locator('#active')).to_be_checked()
    expect(form.locator('#delete, a[href*="/delete/"]')).to_have_count(0)

    expect(page.locator('#timeline')).to_have_value('home')
    for field in ('url', 'user_id'):
        expect(_row(page, field)).to_be_hidden()
        expect(page.locator(f'#{field}')).to_be_disabled()

    page.locator('#timeline').select_option('user')
    for field in ('url', 'user_id'):
        expect(_row(page, field)).to_be_visible()
        expect(page.locator(f'#{field}')).to_be_enabled()

    expect(_row(page, 'basic_user')).to_be_hidden()
    page.locator('#auth').select_option('basic')
    expect(_row(page, 'basic_user')).to_be_visible()
    expect(_row(page, 'basic_pass')).to_be_visible()
    page.locator('#auth').select_option('oauth2')
    expect(_row(page, 'basic_user')).to_be_hidden()
    expect(page.locator('#basic_user')).to_be_disabled()

    page.locator('#cancel').click()
    expect(form).to_be_hidden()


def test_service_form_marks_missing_fields_then_creates_service(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.route(
        '**/settings/api/import',
        lambda route: _json(route, {'queued': True, 'state': None}),
    )
    page.goto(f'{app_base_url}/settings/services')
    page.locator('#add-service a.webfeed').click()
    expect(page.locator('#service-form')).to_be_visible()

    with page.expect_response(
        lambda r: _is_service_api('post')(r.request)
    ) as response_info:
        page.locator('#save').click()
    assert _form(response_info.value.request)['name'] == ['']
    expect(page.locator('#service-form label[for=name]')).to_have_class(
        re.compile(r'\bmissing\b')
    )
    expect(page.locator('#service-form')).to_be_visible()
    expect(page.locator('#edit-service li')).to_have_count(1)
    assert not Service.objects.filter(api='webfeed').exists()

    page.locator('#name').fill('Created Feed')
    page.locator('#url').fill('http://127.0.0.1:9/created.xml')
    with page.expect_request('**/settings/api/import') as import_info:
        page.locator('#save').click()
    expect(page.locator('#edit-service')).to_contain_text('Created Feed')
    expect(page.locator('#service-form label[for=name]')).not_to_have_class(
        re.compile(r'\bmissing\b')
    )
    service = Service.objects.get(name='Created Feed')
    assert _form(import_info.value)['id'] == [str(service.pk)]
    expect(page.locator(f'#service-{service.pk}')).to_have_text('Created Feed')


def test_edit_existing_service_updates_the_list_in_place(
    page: Page, app_base_url: str, ensure_admin_session
):
    service = Service.objects.create(
        api='webfeed', name='Feed To Rename', url='http://127.0.0.1:9/rename.xml'
    )
    ensure_admin_session()
    page.goto(f'{app_base_url}/settings/services')
    link = page.locator(f'#service-{service.pk}')

    with page.expect_request(_is_service_api('get')) as request_info:
        link.click()
    assert _form(request_info.value) == {
        'method': ['get'],
        'id': [str(service.pk)],
    }
    form = page.locator('#service-form')
    expect(form).to_be_visible()
    expect(page.locator('#name')).to_have_value('Feed To Rename')
    expect(form.locator('input[type=hidden][name=id]')).to_have_value(str(service.pk))
    delete = form.get_by_role('link', name='delete')
    expect(delete).to_have_attribute(
        'href', f'/admin/stream/service/{service.pk}/delete/'
    )
    expect(delete).to_have_attribute('target', 'admin')

    page.locator('#name').fill('Renamed Feed')
    with page.expect_response(lambda r: _is_service_api('post')(r.request)) as info:
        page.locator('#save').click()
    sent = _form(info.value.request)
    assert sent['id'] == [str(service.pk)]
    assert sent['api'] == ['webfeed']
    assert sent['name'] == ['Renamed Feed']

    expect(link).to_have_text('Renamed Feed')
    expect(page.locator('#edit-service > li')).to_have_count(2)
    # Replacing the list item drops the form that was open inside it.
    expect(form).to_be_hidden()
    service.refresh_from_db()
    assert service.name == 'Renamed Feed'

    link.click()
    expect(form).to_be_visible()
    expect(page.locator('#name')).to_have_value('Renamed Feed')
    page.locator('#cancel').click()
    expect(form).to_be_hidden()


def test_saved_service_name_is_listed_as_text(
    page: Page, app_base_url: str, ensure_admin_session
):
    name = '<img src=x onerror="window.__injected=1">Feed'
    service = Service.objects.create(
        api='webfeed', name='Plain Feed', url='http://127.0.0.1:9/plain.xml'
    )
    ensure_admin_session()
    page.goto(f'{app_base_url}/settings/services')
    link = page.locator(f'#service-{service.pk}')
    link.click()
    page.locator('#name').fill(name)
    page.locator('#save').click()

    expect(link).to_have_text(name)
    expect(page.locator('#edit-service img')).to_have_count(0)
    assert page.evaluate('window.__injected') is None


@pytest.mark.parametrize(
    ('auth', 'link', 'path'),
    [('oauth', 'oauth_conf', 'oauth'), ('oauth2', 'oauth2_conf', 'oauth2')],
)
def test_configure_access_opens_the_oauth_popup(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    auth: str,
    link: str,
    path: str,
):
    service = Service.objects.create(
        api='mastodon', name='OAuth Service', url='', creds=auth
    )
    ensure_admin_session()
    page.context.route(
        f'**/settings/{path}/{service.pk}',
        lambda route: route.fulfill(status=200, content_type='text/html', body='ok'),
    )
    page.goto(f'{app_base_url}/settings/services')
    page.locator(f'#service-{service.pk}').click()
    expect(page.locator('#auth')).to_have_value(auth)

    with page.expect_popup() as popup_info:
        page.locator(f'#{link}').click()
    popup = popup_info.value
    assert popup.url == f'{app_base_url}/settings/{path}/{service.pk}'
    assert page.url == f'{app_base_url}/settings/services'
    popup.close()


# --- Fetch status -----------------------------------------------------------


class _FetchStub:
    """Stub the fetch endpoints and count status polls."""

    def __init__(self, page: Page, service: Service) -> None:
        self.service = service
        self.polls = 0
        self.state: dict[str, Any] = self.make('idle')
        self.fetch_now: tuple[int, Any] = (200, {'queued': True, 'state': None})
        page.route('**/settings/api/fetch-status*', self._status)
        page.route('**/settings/api/fetch-now', self._fetch_now)

    def make(self, status: str, **fields: Any) -> dict[str, Any]:
        return {'service_id': self.service.pk, 'status': status, **fields}

    def _status(self, route: Route) -> None:
        self.polls += 1
        _json(route, {'services': {str(self.service.pk): self.state}})

    def _fetch_now(self, route: Route) -> None:
        status, body = self.fetch_now
        _json(route, body, status)


def test_run_now_polls_until_the_fetch_finishes(
    page: Page, app_base_url: str, ensure_admin_session
):
    service = Service.objects.create(
        api='webfeed', name='Polled Feed', url='http://feed.invalid/'
    )
    ensure_admin_session()
    stub = _FetchStub(page, service)
    stub.fetch_now = (200, {'queued': True, 'state': stub.make('queued')})
    stub.state = stub.make('running', last_result='Fetching...')
    page.clock.install()
    page.goto(f'{app_base_url}/settings/status')
    row = page.locator(f'#fetch-diagnostics-{service.pk}')
    label = row.locator('.fetch-status')
    button = row.locator('a.run-fetch')
    assert stub.polls == 0

    with page.expect_request('**/settings/api/fetch-now') as request_info:
        button.click()
    assert _form(request_info.value) == {'id': [str(service.pk)]}
    expect(label).to_have_text('running')
    expect(label).to_have_attribute('data-status', 'running')
    expect(button).to_have_attribute('aria-busy', 'true')
    expect(row.locator(f'#fetch-result-{service.pk}')).to_have_text('Fetching...')
    polls = stub.polls

    stub.state = stub.make(
        'succeeded',
        last_result='3 new entries',
        last_succeeded_at='2026-03-01T10:00:00+00:00',
        finished_at='2026-03-01T10:00:00+00:00',
    )
    page.clock.run_for(3000)
    expect(label).to_have_text('succeeded')
    assert stub.polls == polls + 1
    expect(button).to_have_attribute('aria-busy', 'false')
    expect(row.locator(f'#fetch-result-{service.pk}')).to_have_text('3 new entries')
    for cell in ('last-succeeded', 'finished'):
        expect(row.locator(f'#fetch-summary-{cell}-{service.pk}')).not_to_have_text(
            re.compile(r'Never|No completed runs')
        )
    time = row.locator(
        f'#fetch-summary-last-succeeded-{service.pk} '
        'time.fetch-time[datetime="2026-03-01T10:00:00+00:00"]'
    )
    expect(time).to_have_text(re.compile(r' ago$'))
    expect(time).to_have_attribute('data-tooltip', re.compile(r'2026'))
    time.hover()
    tooltip = time.evaluate("el => getComputedStyle(el, '::after').content")
    assert '2026' in tooltip
    expect(row.locator(f'#fetch-error-text-{service.pk}')).to_have_text('—')

    page.clock.run_for(15000)
    page.wait_for_timeout(200)
    assert stub.polls == polls + 1


def test_run_now_error_shows_the_server_message(
    page: Page, app_base_url: str, ensure_admin_session
):
    service = Service.objects.create(
        api='webfeed', name='Broken Feed', url='http://feed.invalid/'
    )
    ensure_admin_session()
    stub = _FetchStub(page, service)
    stub.fetch_now = (400, {'error': 'This service cannot be fetched.'})
    dialogs = _record_dialogs(page, accept=True)
    page.clock.install()
    page.goto(f'{app_base_url}/settings/status')
    row = page.locator(f'#fetch-diagnostics-{service.pk}')

    row.locator('a.run-fetch').click()
    label = row.locator('.fetch-status')
    expect(label).to_have_text('failed')
    expect(label).to_have_attribute('title', 'This service cannot be fetched.')
    expect(row.locator(f'#fetch-error-text-{service.pk}')).to_have_text(
        'This service cannot be fetched.'
    )
    expect(row.locator(f'#fetch-error-{service.pk}')).not_to_have_class(
        re.compile(r'\bempty\b')
    )
    expect(row.locator('a.run-fetch')).to_have_attribute('aria-busy', 'false')
    expect(page.locator('#spinner')).to_have_count(0)
    assert dialogs == []


def test_status_page_polls_on_load_only_while_a_fetch_is_active(
    page: Page, app_base_url: str, ensure_admin_session
):
    from glifestream.stream.models import ServiceFetchState

    idle = Service.objects.create(
        api='webfeed', name='Idle Feed', url='http://a.invalid/'
    )
    ensure_admin_session()
    stub = _FetchStub(page, idle)
    page.clock.install()

    page.goto(f'{app_base_url}/settings/status')
    expect(page.locator(f'#fetch-diagnostics-{idle.pk}')).to_be_visible()
    page.clock.run_for(10000)
    page.wait_for_timeout(200)
    assert stub.polls == 0

    page.goto('about:blank')
    ServiceFetchState.objects.update_or_create(
        service=idle, defaults={'status': ServiceFetchState.STATUS_QUEUED}
    )
    stub.state = stub.make('succeeded', last_result='done')
    with page.expect_request('**/settings/api/fetch-status*'):
        page.goto(f'{app_base_url}/settings/status')
    expect(page.locator(f'#fetch-status-{idle.pk}')).to_have_text('succeeded')


# --- Lists and WebSub -------------------------------------------------------


def test_list_selector_navigates_between_lists(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/settings/lists')

    page.locator('#select-list').select_option('seeded-list')
    expect(page).to_have_url(f'{app_base_url}/settings/lists/seeded-list')
    page.locator('#select-list').select_option('')
    expect(page).to_have_url(f'{app_base_url}/settings/lists')


def test_list_delete_can_be_cancelled(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/settings/lists/seeded-list')
    dialogs = _record_dialogs(page, accept=False)

    page.locator('#list-form a', has_text='delete').click()
    page.wait_for_timeout(300)
    assert dialogs == ['Are you sure?']
    expect(page).to_have_url(f'{app_base_url}/settings/lists/seeded-list')
    assert List.objects.filter(slug='seeded-list').exists()


def test_list_delete_posts_the_form_with_a_delete_flag(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/settings/lists/seeded-list')
    _record_dialogs(page, accept=True)

    with page.expect_request(
        lambda r: r.method == 'POST' and '/settings/lists' in r.url
    ) as request_info:
        page.locator('#list-form a', has_text='delete').click()
    assert _form(request_info.value)['delete'] == ['1']
    expect(page).to_have_url(re.compile(r'/settings/lists/?$'))


@pytest.mark.parametrize('confirm', [True, False])
def test_websub_unsubscribe_asks_and_posts(
    page: Page, app_base_url: str, ensure_admin_session, confirm: bool
):
    subscribed = Service.objects.create(
        api='webfeed', name='Hub Feed', url='http://feed.invalid/hub.xml'
    )
    # The unsubscribe form exists only while some service can still subscribe.
    Service.objects.create(
        api='webfeed', name='Other Feed', url='http://feed.invalid/other.xml'
    )
    sub = WebSub.objects.create(
        hash='a' * 20, service=subscribed, hub='http://hub.invalid/', verified=True
    )
    ensure_admin_session()
    page.goto(f'{app_base_url}/settings/websub')
    dialogs = _record_dialogs(page, accept=confirm)
    posted: list[Request] = []
    page.on(
        'request',
        lambda r: (
            posted.append(r)
            if r.method == 'POST' and r.url.endswith('/settings/websub')
            else None
        ),
    )

    page.locator(f'#unsubscribe-{sub.pk}').click()
    if confirm:
        expect(page.get_by_text('WebSub subscriptions')).to_be_visible()
        page.wait_for_load_state()
        assert len(posted) == 1
        assert _form(posted[0])['unsubscribe'] == [str(sub.pk)]
    else:
        page.wait_for_timeout(300)
        assert posted == []
        expect(page.locator(f'#unsubscribe-{sub.pk}')).to_be_visible()
        expect(page.locator('#websub-form select')).to_be_enabled()
    assert dialogs == ['Are you sure?']
