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
from django.http import HttpRequest
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import clear_script_prefix, resolve, set_script_prefix

from glifestream.stream.templatetags.gls_nav import nav_section


def _request(path: str) -> HttpRequest:
    request = RequestFactory().get(path)
    request.resolver_match = resolve(path)
    return request


@pytest.mark.parametrize(
    ('path', 'section'),
    [
        ('/', 'home'),
        ('/2026/', 'home'),
        ('/2026/10/', 'home'),
        ('/public/', 'public'),
        ('/public/2026/10/12/', 'public'),
        ('/settings/services', 'settings'),
        ('/settings/preferences', 'settings'),
        ('/favorites/', ''),
        ('/favorites/2026/', ''),
        ('/list/friends/', ''),
        ('/list/friends/2026/', ''),
        ('/entry/7', ''),
        ('/login', ''),
    ],
)
def test_nav_section(path: str, section: str):
    assert nav_section(_request(path)) == section


def test_nav_section_under_a_script_prefix():
    """A site served under a path, as BASE_URL makes it, marks the same."""
    set_script_prefix('/gls/')
    try:
        request = RequestFactory().get('/settings/status', SCRIPT_NAME='/gls')
        request.resolver_match = resolve('/settings/status')
        assert request.path == '/gls/settings/status'
        assert nav_section(request) == 'settings'
        request = RequestFactory().get('/public/', SCRIPT_NAME='/gls')
        request.resolver_match = resolve('/public/')
        assert nav_section(request) == 'public'
    finally:
        clear_script_prefix()


def test_nav_section_without_a_resolved_request():
    assert nav_section(None) == ''
    assert nav_section(RequestFactory().get('/')) == ''


def test_nav_current_marks_only_the_link_to_the_page_shown():
    template = Template(
        "{% load gls_nav %}<a{% nav_current 'home' %}></a>"
        "<a{% nav_current 'public' %}></a>"
    )
    html = template.render(Context({'request': _request('/public/')}))
    assert html == '<a></a><a aria-current="page"></a>'
