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

The public JavaScript contract a deployment can rely on.

A site customizes the stream from templates/user-scripts.js (overridden in
run/templates/) by setting globals that glifestream.js reads. These tests set
the same globals through an init script and check that the script honours
them. A rewrite must keep them passing, or change them together with a
documented change to the contract.

  window.user_alter_html(ctx)      called for every batch of entries shown
  window.social_sharing_sites      replaces the share box site list
  window.video_embeds              adds or replaces video providers
  window.audio_embeds              adds audio providers
  window.continuous_reading        entries to load in place before navigating
  window.gls.unhide_entry          used by the "Undo" link markup
  window.gls.run_fetch_service     used by the settings status page markup
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def _articles_in_batches(page: Page) -> list[list[str]]:
    return cast(list[list[str]], page.evaluate('window.__alterBatches'))


def test_user_alter_html_is_called_for_each_batch_of_entries(
    page: Page, app_base_url: str, ensure_admin_session, make_entry, settings
):
    settings.ENTRIES_ON_PAGE = 2
    entries = [make_entry(f'Altered Entry {n}') for n in range(3)]
    page.add_init_script(
        """
        window.__alterBatches = [];
        window.user_alter_html = function(ctx) {
            const nodes = ctx instanceof Element ? [ctx] : Array.from(ctx);
            const ids = nodes.flatMap(n => n.matches('article')
                ? [n.id]
                : Array.from(n.querySelectorAll('article')).map(a => a.id));
            window.__alterBatches.push(ids);
        };
        """
    )
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    first_page = [f'entry-{e.pk}' for e in entries[:2]]
    expect(page.locator('#stream article')).to_have_count(2)
    assert _articles_in_batches(page) == [first_page]

    page.locator('#stream nav a.next').click()
    expect(page.locator('#stream article')).to_have_count(4)
    batches = _articles_in_batches(page)
    assert len(batches) == 2
    assert batches[1][0] == f'entry-{entries[2].pk}'
    assert not set(batches[1]) & set(first_page)


def test_social_sharing_sites_replace_the_default_list(
    page: Page, app_base_url: str, ensure_admin_session, make_entry
):
    entry = make_entry('Custom Share Entry')
    page.add_init_script(
        """
        window.social_sharing_sites = [{
            name: 'Toot',
            href: 'https://toot.example/share?text={TITLE}%20{URL}',
            className: 'mastodon'
        }, {
            name: 'Icon Site',
            href: 'https://icon.example/?u={URL}',
            icon: '/static/icon.png'
        }];
        """
    )
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    page.locator(f'#entry-{entry.pk} a.shareit').click()
    box = page.locator('#shareitbox')
    expect(box).to_be_visible()
    for default in ('E-mail', 'Twitter', 'Facebook', 'Reddit'):
        expect(box.locator('.item a', has_text=default)).to_have_count(0)

    toot = box.locator('.item a', has_text='Toot')
    href = toot.get_attribute('href') or ''
    assert href.startswith('https://toot.example/share?text=Custom%20Share%20Entry%20')
    assert f'%2Fentry%2F{entry.pk}' in href
    expect(toot.locator('span.share-mastodon')).to_have_count(1)

    icon_site = box.locator('.item a', has_text='Icon Site')
    expect(icon_site.locator('img')).to_have_attribute('src', '/static/icon.png')


def test_video_embeds_add_string_and_function_providers(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    make_entry,
    stub_external_requests,
):
    make_entry(
        'Custom Video Entry',
        '<div data-id="peertube-abc123" class="play-video"><a href="#">peertube</a>'
        '<div class="playbutton"></div></div>'
        '<div data-id="custom-xyz" data-extra="from-markup" class="play-video">'
        '<a href="#">custom</a><div class="playbutton"></div></div>',
    )
    page.add_init_script(
        """
        window.video_embeds = {
            peertube: '<iframe src="https://peertube.example/embed/{ID}"></iframe>',
            custom: function(wrapper, id) {
                return {
                    html: '<p class="custom-embed">' + id + ':' +
                        wrapper.getAttribute('data-extra') + '</p>',
                    style: 'padding-bottom:50%'
                };
            }
        };
        """
    )
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    page.locator('[data-id="peertube-abc123"]').click()
    expect(page.locator('div.player.video.peertube iframe')).to_have_attribute(
        'src', 'https://peertube.example/embed/abc123'
    )

    page.locator('[data-id="custom-xyz"]').click()
    player = page.locator('div.player.video.custom')
    expect(player.locator('p.custom-embed')).to_have_text('xyz:from-markup')
    expect(player).to_have_attribute('style', 'padding-bottom:50%')

    # The built-in providers are still there.
    page.evaluate(
        """() => document.querySelector('#stream article').insertAdjacentHTML(
            'beforeend',
            '<div data-id="youtube-keepme" class="play-video"><a href="#">yt</a>' +
            '<div class="playbutton"></div></div>')"""
    )
    page.locator('[data-id="youtube-keepme"]').click()
    expect(page.locator('div.player.video.youtube iframe')).to_have_attribute(
        'src', 'https://www.youtube.com/embed/keepme?autoplay=1&rel=0'
    )


def test_audio_embeds_add_providers(
    page: Page,
    app_base_url: str,
    ensure_admin_session,
    make_entry,
    stub_external_requests,
):
    make_entry(
        'Custom Audio Entry',
        '<p><span data-id="soundbox-track42" class="play-audio">'
        '<a href="https://soundbox.example/track42">listen</a></span></p>',
    )
    page.add_init_script(
        """
        window.audio_embeds = {
            soundbox: '<iframe src="https://soundbox.example/embed/{ID}"></iframe>'
        };
        """
    )
    ensure_admin_session()
    page.goto(f'{app_base_url}/')
    trigger = page.locator('[data-id="soundbox-track42"]')

    trigger.click()
    expect(page.locator('.player.audio iframe')).to_have_attribute(
        'src', 'https://soundbox.example/embed/track42'
    )
    assert page.url == f'{app_base_url}/'
    trigger.click()
    expect(page.locator('.player.audio')).to_have_count(0)


def test_continuous_reading_zero_turns_paging_into_navigation(
    page: Page, app_base_url: str, ensure_admin_session, make_entry, settings
):
    settings.ENTRIES_ON_PAGE = 2
    for n in range(3):
        make_entry(f'Navigated Entry {n}')
    page.add_init_script('window.continuous_reading = 0;')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    page.locator('#stream nav a.next').click()
    page.wait_for_url(f'{app_base_url}/?start=*')
    expect(page.locator('#stream article').first).to_contain_text('Navigated Entry 2')


def test_continuous_reading_limit_switches_to_navigation(
    page: Page, app_base_url: str, ensure_admin_session, make_entry, settings
):
    settings.ENTRIES_ON_PAGE = 2
    for n in range(5):
        make_entry(f'Limited Entry {n}')
    page.add_init_script('window.continuous_reading = 3;')
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    page.locator('#stream nav a.next').click()
    expect(page.locator('#stream article')).to_have_count(4)
    assert page.url == f'{app_base_url}/'

    page.locator('#stream nav a.next').click()
    page.wait_for_url(f'{app_base_url}/?start=*')
    expect(page.locator('#stream article').first).to_contain_text('Limited Entry 4')


def test_gls_namespace_exposes_markup_callbacks(
    page: Page, app_base_url: str, ensure_admin_session
):
    ensure_admin_session()
    page.goto(f'{app_base_url}/')

    kinds: dict[str, Any] = page.evaluate(
        """() => ({
            unhide_entry: typeof window.gls.unhide_entry,
            run_fetch_service: typeof window.gls.run_fetch_service,
        })"""
    )
    assert kinds == {'unhide_entry': 'function', 'run_fetch_service': 'function'}
