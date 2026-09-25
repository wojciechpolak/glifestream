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

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

from glifestream.utils.common import static_url


def _icon_files() -> list[str]:
    return [
        settings.FAVICON,
        settings.APPLE_TOUCH_ICON,
        *(icon['src'] for icon in settings.PWA_APP_ICONS),
    ]


@pytest.mark.parametrize('path', _icon_files())
def test_every_configured_icon_is_a_static_file(path):
    assert finders.find(path), path


@pytest.mark.django_db
def test_the_page_links_the_favicon_and_the_apple_touch_icon(client):
    html = client.get('/').content.decode()

    assert f'<link rel="icon" href="{static(settings.FAVICON)}">' in html
    assert (
        f'<link rel="apple-touch-icon" href="{static(settings.APPLE_TOUCH_ICON)}">'
        in html
    )


def test_the_web_manifest_offers_a_maskable_icon(client):
    icons = client.get('/manifest.webmanifest').json()['icons']

    assert [icon['src'] for icon in icons] == [
        static(icon['src']) for icon in settings.PWA_APP_ICONS
    ]
    assert any(icon.get('purpose') == 'maskable' for icon in icons)


@pytest.mark.django_db
def test_the_icons_follow_a_static_url_set_after_the_base_settings(client, settings):
    # A settings module that imports glifestream.settings and then serves
    # the site under a path prefix, as a Docker deployment does.
    settings.STATIC_URL = '/stream/static/'

    html = client.get('/').content.decode()
    icons = client.get('/manifest.webmanifest').json()['icons']

    assert 'href="/stream/static/apple-touch-icon' in html
    assert 'href="/stream/static/favicon' in html
    assert all(icon['src'].startswith('/stream/static/') for icon in icons)


@pytest.mark.parametrize('url', ['/favicon.ico', 'https://cdn.example.org/favicon.ico'])
def test_an_icon_set_as_a_url_is_used_as_it_is(url):
    assert static_url(url) == url
