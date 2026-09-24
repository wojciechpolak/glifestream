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

The Content Security Policy, and the pages it lets run as they are.
"""

from __future__ import annotations

import copy
import os
import re
from html.parser import HTMLParser

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

import glifestream.settings as project_settings
from glifestream.settings_csp import csp_settings
from glifestream.stream.models import Service


@pytest.mark.skipif(
    'CONTENT_SECURITY_POLICY' in os.environ, reason='the environment sets the mode'
)
def test_the_site_only_reports_by_default():
    # The tests themselves enforce it; see enforce_csp in conftest.py.
    assert project_settings.CONTENT_SECURITY_POLICY == 'report-only'
    assert project_settings.SECURE_CSP == {}
    assert project_settings.SECURE_CSP_REPORT_ONLY['script-src']


def test_enforce_mode_sends_the_policy():
    enforce, report_only = csp_settings('enforce', static_url='/static/')

    assert enforce['script-src'] == ["'self'", '<CSP_NONCE_SENTINEL>']
    assert enforce['object-src'] == ["'none'"]
    assert report_only == {}


def test_report_only_mode_only_reports():
    enforce, report_only = csp_settings(' Report-Only ', static_url='/static/')

    assert enforce == {}
    assert report_only['default-src'] == ["'self'"]


def test_off_mode_sends_nothing():
    assert csp_settings('off', static_url='/static/') == ({}, {})


def test_an_unknown_mode_fails_at_startup():
    with pytest.raises(ValueError, match='CONTENT_SECURITY_POLICY'):
        csp_settings('strict', static_url='/static/')


def test_static_files_on_another_site_are_allowed():
    enforce, _ = csp_settings('enforce', static_url='https://cdn.example.org/gls/')

    assert 'https://cdn.example.org' in enforce['script-src']
    assert 'https://cdn.example.org' in enforce['style-src']
    assert 'https://cdn.example.org' in enforce['font-src']


@pytest.mark.django_db
def test_pages_carry_the_policy(client):
    response = client.get(reverse('index'))

    policy = response.headers['Content-Security-Policy']
    assert "script-src 'self';" in policy
    assert "object-src 'none'" in policy


@pytest.mark.django_db
def test_a_user_script_runs_with_the_request_nonce(client, settings, tmp_path):
    (tmp_path / 'user-scripts.js').write_text(
        '<script nonce="{{ csp_nonce }}">window.custom = 1;</script>'
    )
    templates = copy.deepcopy(settings.TEMPLATES)
    templates[0]['DIRS'] = [str(tmp_path), *templates[0]['DIRS']]
    settings.TEMPLATES = templates

    response = client.get(reverse('index'))

    nonce = re.search(r'<script nonce="([^"]+)">window.custom', response.text)
    assert nonce
    policy = response.headers['Content-Security-Policy']
    assert f"script-src 'self' 'nonce-{nonce.group(1)}'" in policy


class _InlineCode(HTMLParser):
    """What a policy without 'unsafe-inline' scripts would block."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == 'script' and not values.get('src'):
            if values.get('type') != 'application/json':
                self.found.append(f'inline <script> {values}')
        for name, value in attrs:
            if name.startswith('on'):
                self.found.append(f'<{tag} {name}="{value}">')
            if name in ('href', 'action') and (value or '').startswith('javascript:'):
                self.found.append(f'<{tag} {name}="{value}">')


def inline_code(html: str) -> list[str]:
    parser = _InlineCode()
    parser.feed(html)
    return parser.found


@pytest.mark.django_db
def test_pages_have_no_inline_script(client, admin_client):
    Service.objects.create(name='Feed', api='webfeed', url='http://example.com/f')
    pages = {
        'stream': client.get(reverse('index')),
        'login': client.get(reverse('login')),
        'not found': client.get('/no-such-page/'),
        'own stream': admin_client.get(reverse('index')),
        'services': admin_client.get(reverse('usettings-services')),
        'status': admin_client.get(reverse('usettings-status')),
        'lists': admin_client.get(reverse('usettings-lists')),
        'websub': admin_client.get(reverse('usettings-websub')),
    }

    for name, response in pages.items():
        assert response.status_code in (200, 404), name
        assert inline_code(response.text) == [], name
    assert 'class="run-fetch"' in pages['status'].text


@pytest.mark.parametrize('template', ['oauth.html', 'oauth2.html'])
def test_oauth_pages_have_no_inline_script(template):
    request = RequestFactory().get('/')
    html = render_to_string(
        template, {'phase': 3, 'page': {'title': 'OAuth'}}, request=request
    )

    assert 'data-close-window' in html
    assert inline_code(html) == []
