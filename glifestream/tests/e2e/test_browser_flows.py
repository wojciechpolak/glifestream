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

import pytest
from playwright.sync_api import Locator, Page, expect

from glifestream.stream.models import Entry, Service


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
