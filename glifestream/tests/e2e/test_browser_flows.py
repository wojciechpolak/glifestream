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

import re
from typing import cast

import pytest
from playwright.sync_api import Locator, Page, expect

from glifestream.gauth.models import OAuthClient
from glifestream.stream.models import Entry, Service
from glifestream.tests.e2e.conftest import MOCK_ATPROTO_ACCESS_JWT


pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def _entry_article(page: Page, title: str) -> Locator:
    return page.locator('article', has_text=title).first


def _open_entry_menu(article: Locator) -> None:
    article.locator('span.entry-controls-switch').click()


def _is_settings_service_response(response, *, method: str) -> bool:
    if not response.url.endswith('/settings/api/service'):
        return False
    if response.request.method != 'POST':
        return False

    post_data = response.request.post_data or ''
    return f'method={method}' in post_data


def test_initial_admin_login_requires_password_change(
    page: Page,
    app_base_url: str,
    login_as_initial_admin,
    finish_forced_password_change,
    vrt,
):
    login_as_initial_admin()

    expect(page.get_by_role('heading', name='Change Your Password')).to_be_visible()
    finish_forced_password_change()

    expect(page).to_have_url(f'{app_base_url}/')
    expect(page.get_by_text('Seeded Private Entry')).to_be_visible()
    vrt.screenshot(
        page,
        'main-stream.png',
        full_page=True,
        mask=[page.locator('#calendar')],
    )


def test_invalid_login_and_logout(
    page: Page,
    app_base_url: str,
    login_as_initial_admin,
    finish_forced_password_change,
):
    page.goto(f'{app_base_url}/login')
    page.get_by_label('Username').fill('admin')
    page.get_by_label('Password').fill('wrong-password')
    page.get_by_role('button', name='Log In').click()

    expect(page.get_by_text('Invalid username or password')).to_be_visible()

    login_as_initial_admin()
    finish_forced_password_change()
    page.get_by_text('Logout').click()

    expect(page.get_by_text('Login')).to_be_visible()


def test_worker_ingests_mocked_feeds_and_updates_browser_state(
    page: Page,
    app_base_url: str,
    mock_feed_server,
    create_webfeed_service,
    run_worker,
    ensure_admin_session,
    vrt,
):
    public_url = mock_feed_server.publish_fixture('feeds/public.xml', 'initial-rss.xml')
    private_url = mock_feed_server.publish_fixture(
        'feeds/private.xml', 'initial-atom.xml'
    )

    create_webfeed_service('Playwright Public Feed', public_url, public=True)
    create_webfeed_service('Playwright Private Feed', private_url, public=False)

    run_worker('--api=webfeed', '--force-check')

    assert Entry.objects.filter(title='Public RSS Entry').exists()
    assert Entry.objects.filter(title='Private Atom Entry').exists()

    page.goto(f'{app_base_url}/public/')
    expect(page.get_by_text('Public RSS Entry')).to_be_visible()
    expect(page.get_by_text('Private Atom Entry', exact=True)).to_have_count(0)
    vrt.screenshot(
        page,
        'public-stream.png',
        full_page=True,
        mask=[page.locator('#calendar')],
    )

    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    expect(page.get_by_text('Public RSS Entry')).to_be_visible()
    expect(page.get_by_text('Private Atom Entry')).to_be_visible()

    article = _entry_article(page, 'Public RSS Entry')
    _open_entry_menu(article)
    with page.expect_response(
        lambda response: (
            response.url.endswith('/api/favorite') and response.request.method == 'POST'
        )
    ):
        article.get_by_text('Favorite', exact=True).click()

    page.goto(f'{app_base_url}/favorites/')
    expect(page.get_by_text('Public RSS Entry')).to_be_visible()

    article = _entry_article(page, 'Public RSS Entry')
    _open_entry_menu(article)
    with page.expect_response(
        lambda response: (
            response.url.endswith('/api/unfavorite')
            and response.request.method == 'POST'
        )
    ):
        article.get_by_text('Unfavorite', exact=True).click()
    page.reload()
    expect(page.get_by_text('Public RSS Entry', exact=True)).to_have_count(0)

    mock_feed_server.publish_fixture('feeds/public.xml', 'updated-rss.xml')
    run_worker('--api=webfeed', '--force-check')

    assert Entry.objects.filter(title='Public RSS Entry Two').exists()

    page.goto(f'{app_base_url}/public/')
    expect(page.get_by_text('Public RSS Entry Two')).to_be_visible()


def test_mastodon_oauth2_full_flow_ingests_stream_updates(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    mock_oauth2_server,
    run_worker,
):
    ensure_admin_session()

    page.goto(f'{app_base_url}/settings/services')
    page.locator('#add-service a.mastodon').click()
    expect(page.locator('#service-form')).to_be_visible()

    page.locator('#name').fill('Playwright Mastodon')
    page.locator('#timeline').select_option('home')
    page.locator('#auth').select_option('oauth2')
    page.locator('#home').check()
    page.locator('#active').check()
    with page.expect_response(
        lambda response: _is_settings_service_response(response, method='post')
    ):
        page.locator('#save').click()

    expect(page.locator('#edit-service')).to_contain_text('Playwright Mastodon')
    expect(page.locator('#oauth2_conf')).to_be_visible()

    service = Service.objects.get(name='Playwright Mastodon')
    service_id = cast(int, service.pk)
    assert service.home is True
    assert service.active is True
    service.url = mock_oauth2_server.base_url
    service.save(update_fields=['url'])

    with page.expect_popup() as popup_info:
        page.locator('#oauth2_conf').click()

    popup = popup_info.value
    popup.wait_for_load_state()
    expect(popup.get_by_text('OAuth 2.0: Playwright Mastodon')).to_be_visible()
    popup.locator('#identifier').fill('playwright-client')
    popup.locator('#secret').fill('playwright-secret')
    popup.get_by_role('button', name='Next step').click()

    expect(popup).to_have_url(
        re.compile(rf'^{re.escape(mock_oauth2_server.base_url)}/oauth/authorize')
    )
    popup.locator('#authorize').click()

    expect(popup).to_have_url(
        re.compile(rf'^{re.escape(app_base_url)}/settings/oauth2/{service_id}$')
    )
    expect(
        popup.get_by_text('Your OAuth 2.0 access setup is completed.')
    ).to_be_visible()
    popup.close()

    oauth_client = OAuthClient.objects.get(service=service)
    assert oauth_client.phase == 3
    assert oauth_client.token == 'gls-e2e-access-token'
    assert len(mock_oauth2_server.token_requests) == 1

    mock_oauth2_server.api_requests.clear()
    run_worker('--api=mastodon', '--force-check')

    assert (
        Entry.objects.filter(
            service=service, title='Playwright Mastodon Entry One'
        ).count()
        == 1
    )
    assert len(mock_oauth2_server.api_requests) == 1
    assert (
        mock_oauth2_server.api_requests[0]['headers'].get('Authorization')
        == 'Bearer gls-e2e-access-token'
    )

    page.goto(f'{app_base_url}/?refresh=oauth2-initial')
    expect(page.get_by_text('Playwright Mastodon Entry One')).to_be_visible()

    mock_oauth2_server.set_home_timeline('home-updated.json')
    run_worker('--api=mastodon', '--force-check')

    assert Entry.objects.filter(service=service).count() == 2
    assert (
        Entry.objects.filter(
            service=service, title='Playwright Mastodon Entry One'
        ).count()
        == 1
    )
    assert (
        Entry.objects.filter(
            service=service, title='Playwright Mastodon Entry Two'
        ).count()
        == 1
    )
    assert len(mock_oauth2_server.api_requests) == 2

    page.goto(f'{app_base_url}/?refresh=oauth2-updated')
    expect(page.get_by_text('Playwright Mastodon Entry Two')).to_be_visible()
    expect(page.get_by_text('Playwright Mastodon Entry One')).to_be_visible()


def test_bluesky_atproto_full_flow_ingests_stream_updates(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    mock_atproto_server,
    configure_mock_atproto_client,
    run_worker,
):
    ensure_admin_session()
    configure_mock_atproto_client(mock_atproto_server.base_url)

    page.goto(f'{app_base_url}/settings/services')
    page.locator('#add-service a.atproto').click()
    expect(page.locator('#service-form')).to_be_visible()

    page.locator('#name').fill('Playwright Bluesky')
    page.locator('#timeline').select_option('home')
    page.locator('#auth').select_option('basic')
    page.locator('#basic_user').fill('playwright.test')
    page.locator('#basic_pass').fill('playwright-app-password')
    page.locator('#home').check()
    page.locator('#active').check()
    with page.expect_response(
        lambda response: (
            response.url.endswith('/settings/api/import')
            and response.request.method == 'POST'
        )
    ):
        with page.expect_response(
            lambda response: _is_settings_service_response(response, method='post')
        ):
            page.locator('#save').click()

    expect(page.locator('#edit-service')).to_contain_text('Playwright Bluesky')

    service = Service.objects.get(name='Playwright Bluesky')
    assert service.home is True
    assert service.active is True
    assert service.creds == 'playwright.test:playwright-app-password'

    mock_atproto_server.session_requests.clear()
    mock_atproto_server.profile_requests.clear()
    mock_atproto_server.timeline_requests.clear()
    run_worker('--api=atproto', '--force-check')

    assert len(mock_atproto_server.session_requests) == 1
    assert (
        mock_atproto_server.session_requests[0]['payload']['identifier']
        == 'playwright.test'
    )
    assert (
        mock_atproto_server.session_requests[0]['payload']['password']
        == 'playwright-app-password'
    )
    assert len(mock_atproto_server.profile_requests) == 1
    assert len(mock_atproto_server.timeline_requests) == 1
    assert (
        mock_atproto_server.timeline_requests[0]['headers'].get('Authorization')
        == f'Bearer {MOCK_ATPROTO_ACCESS_JWT}'
    )
    assert (
        Entry.objects.filter(
            service=service, title='Playwright Bluesky Entry One'
        ).count()
        == 1
    )

    page.goto(f'{app_base_url}/?refresh=atproto-initial')
    expect(page.get_by_text('Playwright Bluesky Entry One')).to_be_visible()

    mock_atproto_server.set_timeline('timeline-updated.json')
    run_worker('--api=atproto', '--force-check')

    assert Entry.objects.filter(service=service).count() == 2
    assert (
        Entry.objects.filter(
            service=service, title='Playwright Bluesky Entry One'
        ).count()
        == 1
    )
    assert (
        Entry.objects.filter(
            service=service, title='Playwright Bluesky Entry Two'
        ).count()
        == 1
    )
    assert len(mock_atproto_server.session_requests) == 2
    assert len(mock_atproto_server.timeline_requests) == 2

    page.goto(f'{app_base_url}/?refresh=atproto-updated')
    expect(page.get_by_text('Playwright Bluesky Entry Two')).to_be_visible()
    expect(page.get_by_text('Playwright Bluesky Entry One')).to_be_visible()


def test_settings_services_lists_and_websub(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    vrt,
):
    ensure_admin_session()

    page.goto(f'{app_base_url}/settings/services')
    expect(page.get_by_text('Seeded Notes')).to_be_visible()

    page.locator('#add-service a.webfeed').click()
    expect(page.locator('#service-form')).to_be_visible()
    page.locator('#name').fill('Playwright Service')
    page.locator('#url').fill('http://127.0.0.1:9/feed.xml')
    page.locator('#public').check()
    page.locator('#save').click()
    expect(page.locator('#edit-service')).to_contain_text('Playwright Service')

    with page.expect_response(
        lambda response: _is_settings_service_response(response, method='get')
    ):
        page.locator('#edit-service a', has_text='Playwright Service').click()
    expect(page.locator('#service-form')).to_be_visible()
    vrt.screenshot(
        page.locator('#settings'),
        'settings-services.png',
    )
    page.locator('#name').fill('Playwright Service Updated')
    with page.expect_response(
        lambda response: _is_settings_service_response(response, method='post')
    ):
        page.locator('#save').click()
    assert Service.objects.filter(name='Playwright Service Updated').exists()
    page.goto(f'{app_base_url}/settings/services')
    expect(page.locator('#edit-service')).to_contain_text('Playwright Service Updated')

    page.goto(f'{app_base_url}/settings/lists')
    page.locator('#id_name').fill('Playwright List')
    page.locator('#id_services').select_option(label='Playwright Service Updated')
    page.get_by_role('button', name='Save').click()

    expect(page).to_have_url(re.compile(r'/settings/lists/playwright-list/?$'))
    expect(page.locator('#select-list')).to_contain_text('Playwright List')

    page.locator('#id_name').fill('Playwright List Updated')
    page.locator('#id_services').select_option(label='Playwright Service Updated')
    page.get_by_role('button', name='Save').click()

    expect(page).to_have_url(re.compile(r'/settings/lists/playwright-list-updated/?$'))
    expect(page.locator('#select-list')).to_contain_text('Playwright List Updated')
    vrt.screenshot(page.locator('#settings'), 'settings-lists.png')

    page.on('dialog', lambda dialog: dialog.accept())
    page.locator('#list-form a', has_text='delete').click()

    expect(page).to_have_url(re.compile(r'/settings/lists/?$'))
    expect(page.locator('#select-list')).not_to_contain_text('Playwright List Updated')

    page.goto(f'{app_base_url}/settings/websub')
    expect(page.locator('#websub-form')).to_be_visible()
    expect(page.get_by_role('link', name='WebSub')).to_be_visible()

    assert Service.objects.filter(name='Playwright Service Updated').exists()
