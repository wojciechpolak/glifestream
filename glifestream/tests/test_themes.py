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

import functools
import re
from pathlib import Path

import pytest
import sass  # type: ignore[import-untyped]
from django.http import HttpRequest

from glifestream.gls_staticfiles import check_themes
from glifestream.settings_themes import (
    BUNDLED_THEMES,
    add_theme_bundles,
    theme_bundle,
)
from glifestream.stream.models import API_LIST, DEFAULT_CLASSES
from glifestream.utils.common import default_theme, get_theme, theme_cycle

THEMES_DIR = Path(__file__).resolve().parents[1] / 'static' / 'themes'

# The themes built on themes/_kit/; `default` predates it.
KIT_THEMES = tuple(name for name in BUNDLED_THEMES if name != 'default')

# What the page script and the markup count on a theme to draw: the kit's.
CONTRACT_SELECTORS = (
    # The top bar folds its links into a menu at 920px and below (navtop.ts).
    '.navtop-toggle',
    '#navtop.open .navtop-menu',
    # The sidebar is a drawer at 640px and below (stream/init.ts).
    '#sidebar-toggle',
    '#sidebar.expanded',
    '#pull-to-refresh',
    'body.pull-refresh-active',
    # Long entries fold to --fold-lines lines (folding.ts).
    '.entry-content.folded',
    'var(--fold-lines',
    '.show-more',
    '.menu-expanded',
    '.entry-controls',
    # More than two themes: "Change theme" opens a list (sidebar.ts).
    '#theme-menu',
    '#share.share-collapsed',
    '.entry-highlight',
    '.entry-preview',
    '.scroll-to-top',
    '#shortcuts-help',
    '.music-card',
    '.thumbnails.atproto-gallery',
    '.editor-toolbar',
    '#status-editor .ProseMirror',
    '#settings',
    'ul.tabs',
    '#loginbox',
    '.pswp',
)

BREAKPOINTS = ('max-width:640px', 'max-width:820px', 'max-width:920px')

# The classes a service can have, each with an icon in every theme.
SERVICE_CLASSES = sorted(
    {api for api, _name in API_LIST}
    | set(DEFAULT_CLASSES.values())
    | {'blog', 'links', 'music', 'reviews'}
)


@functools.cache
def compiled(name: str) -> str:
    css: str = sass.compile(
        filename=str(THEMES_DIR / name / 'style.scss'), output_style='compressed'
    )
    return css


def _request(cookie: str | None = None) -> HttpRequest:
    request = HttpRequest()
    request.COOKIES = {'gls-theme': cookie} if cookie else {}
    return request


class TestThemeChoice:
    def test_the_first_theme_is_the_default(self, settings):
        settings.THEMES = ('riso', 'default')
        settings.DEFAULT_THEME = ''
        assert default_theme() == 'riso'
        assert get_theme(_request()) == 'riso'

    def test_default_theme_picks_another(self, settings):
        settings.THEMES = ('default', 'broadsheet', 'riso')
        settings.DEFAULT_THEME = 'riso'
        assert get_theme(_request()) == 'riso'
        assert get_theme(_request('broadsheet')) == 'broadsheet'

    def test_a_default_theme_not_in_themes_gives_way(self, settings):
        settings.THEMES = ('default', 'riso')
        settings.DEFAULT_THEME = 'phosphor'
        assert default_theme() == 'default'

    def test_a_cookie_for_a_theme_taken_out_falls_back(self, settings):
        settings.THEMES = ('default', 'riso')
        settings.DEFAULT_THEME = 'riso'
        assert get_theme(_request('phosphor')) == 'riso'
        assert get_theme(_request('../default')) == 'riso'

    def test_the_cycle_starts_from_the_default(self, settings):
        settings.THEMES = ('default', 'broadsheet', 'phosphor', 'riso')
        settings.DEFAULT_THEME = 'phosphor'
        assert theme_cycle() == ['phosphor', 'riso', 'default', 'broadsheet']
        settings.DEFAULT_THEME = ''
        assert theme_cycle() == ['default', 'broadsheet', 'phosphor', 'riso']


@pytest.mark.django_db
class TestThemeMenu:
    def test_more_than_two_themes_are_listed(self, client, settings):
        settings.THEMES = ('default', 'broadsheet', 'riso')
        settings.DEFAULT_THEME = ''
        client.cookies['gls-theme'] = 'riso'
        html = client.get('/public/').content.decode()
        assert 'aria-haspopup="true" aria-expanded="false"' in html
        assert re.findall(r'data-theme="([^"]+)"', html) == [
            'default',
            'broadsheet',
            'riso',
        ]
        assert re.findall(r'data-theme="([^"]+)" aria-current="true"', html) == ['riso']

    def test_two_themes_switch_without_a_list(self, client, settings):
        settings.THEMES = ('default', 'riso')
        settings.DEFAULT_THEME = ''
        html = client.get('/public/').content.decode()
        assert 'id="change-theme"' in html
        assert 'aria-haspopup' not in html
        assert 'id="theme-menu"' not in html


class TestThemeBundles:
    def test_every_bundled_theme_has_a_bundle(self, settings):
        for name in BUNDLED_THEMES:
            assert settings.PIPELINE['STYLESHEETS'][name] == theme_bundle(name)

    def test_a_theme_of_its_own_is_built_from_its_directory(self):
        stylesheets = {'kept': {'source_filenames': ('x.css',)}}
        add_theme_bundles(stylesheets, ['kept', 'mine'])
        assert stylesheets['kept'] == {'source_filenames': ('x.css',)}
        assert stylesheets['mine']['source_filenames'][-1] == ('themes/mine/style.scss')
        assert stylesheets['mine']['output_filename'] == 'themes/mine/style.css'


class TestThemeChecks:
    def test_the_bundled_themes_pass(self, settings):
        settings.THEMES = BUNDLED_THEMES
        settings.DEFAULT_THEME = 'riso'
        assert check_themes() == []

    def test_no_theme(self, settings):
        settings.THEMES = ()
        assert [e.id for e in check_themes()] == ['glifestream.E002']

    def test_a_name_it_cannot_go_by(self, settings):
        settings.THEMES = ('default', '../etc', 'Riso')
        settings.DEFAULT_THEME = ''
        assert [e.id for e in check_themes()] == ['glifestream.E003'] * 2

    def test_a_default_theme_not_in_themes(self, settings):
        settings.THEMES = ('default',)
        settings.DEFAULT_THEME = 'riso'
        assert [e.id for e in check_themes()] == ['glifestream.E004']


@pytest.mark.parametrize('name', KIT_THEMES)
class TestKitThemes:
    def test_it_draws_what_the_page_counts_on(self, name):
        css = compiled(name)
        missing = [s for s in CONTRACT_SELECTORS if s not in css]
        assert missing == []

    def test_it_lays_out_every_width(self, name):
        css = compiled(name).replace(' ', '')
        assert [b for b in BREAKPOINTS if b not in css] == []

    def test_it_has_light_and_dark(self, name):
        assert 'prefers-color-scheme:dark' in compiled(name).replace(' ', '')

    def test_every_service_class_has_an_icon(self, name):
        css = compiled(name)
        missing = [
            c for c in SERVICE_CLASSES if not re.search(rf'\.e-{c}(?![\w-])', css)
        ]
        assert missing == []

    def test_it_loads_nothing_from_elsewhere(self, name):
        css = compiled(name)
        assert '@import' not in css
        # A picture drawn in a data: URL may name its own parts by url(#id).
        css = re.sub(r'url\(\s*"data:[^"]*"\s*\)', '', css)
        css = re.sub(r"url\(\s*'data:[^']*'\s*\)", '', css)
        urls = re.findall(r'url\(\s*["\']?([^"\')]+)', css)
        assert urls
        for url in urls:
            if url.startswith('data:'):
                continue
            # Font Awesome's, or a font of the theme's own.
            assert url.startswith(('../../fontawesome/webfonts/', 'fonts/')), url
            assert (THEMES_DIR / name / url.split('?')[0]).resolve().is_file(), url
        # A font of the theme's own is a woff2 from its fonts/, which carries
        # the font's licence.
        for face in re.findall(r'@font-face\{[^}]*\}', css):
            if 'Font Awesome' in face:
                continue
            sources = re.findall(r'url\(\s*["\']?([^"\')]+)', face)
            assert sources, face
            assert all(
                src.startswith('fonts/') and src.endswith('.woff2') for src in sources
            ), face
            assert (THEMES_DIR / name / 'fonts' / 'OFL.txt').is_file()
