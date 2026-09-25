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


def _icon_urls() -> list[str]:
    return [
        settings.FAVICON,
        settings.APPLE_TOUCH_ICON,
        *(icon['src'] for icon in settings.PWA_APP_ICONS),
    ]


@pytest.mark.parametrize('url', _icon_urls())
def test_every_configured_icon_is_a_static_file(url):
    assert url.startswith(settings.STATIC_URL)
    assert finders.find(url.removeprefix(settings.STATIC_URL)), url


@pytest.mark.django_db
def test_the_page_links_the_favicon_and_the_apple_touch_icon(client):
    html = client.get('/').content.decode()

    assert f'<link rel="icon" href="{settings.FAVICON}">' in html
    assert f'<link rel="apple-touch-icon" href="{settings.APPLE_TOUCH_ICON}">' in html


def test_the_web_manifest_offers_a_maskable_icon(client):
    icons = client.get('/manifest.webmanifest').json()['icons']

    assert icons == settings.PWA_APP_ICONS
    assert any(icon.get('purpose') == 'maskable' for icon in icons)
