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

What the page script reads from the page, written as JSON with json_script.

frontend/src/api-types.ts describes both objects, and
glifestream/tests/test_frontend_contract.py checks them; change them together.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.conf import settings
from django.template import Context, Library
from django.template.defaultfilters import date as date_filter
from django.urls import reverse
from django.utils import timezone
from django.utils.html import json_script
from django.utils.safestring import SafeString
from django.utils.translation import gettext, gettext_noop

register = Library()

# Every message the page script translates with _().
MESSAGES = (
    gettext_noop('Are you sure?'),
    gettext_noop('Click and Listen'),
    gettext_noop('Communication Error. Try again.'),
    gettext_noop('Entry hidden'),
    gettext_noop('Favorite'),
    gettext_noop('Fetch queued.'),
    gettext_noop('Keep the original author?'),
    gettext_noop('Never'),
    gettext_noop('Next year'),
    gettext_noop('No completed runs'),
    gettext_noop('Not scheduled'),
    gettext_noop('Previous year'),
    gettext_noop('Pull to refresh'),
    gettext_noop('Refreshing...'),
    gettext_noop('Release to refresh'),
    gettext_noop('Reshare it at your stream'),
    gettext_noop('Share or bookmark this entry'),
    gettext_noop('Unable to queue fetch.'),
    gettext_noop('Undo'),
    gettext_noop('Unfavorite'),
    gettext_noop('Unfavorite this entry before hiding it.'),
    gettext_noop('You are about to re-share this entry at your stream. Confirm?'),
    gettext_noop('Your browser does not support it.'),
    gettext_noop('failed'),
    gettext_noop('idle'),
    gettext_noop('or elsewhere:'),
    gettext_noop('queued'),
    gettext_noop('running'),
    gettext_noop('succeeded'),
)


def page_config() -> dict[str, Any]:
    """PageConfig in api-types.ts."""
    return {
        'baseurl': reverse('index'),
        'maps_engine': settings.MAPS_ENGINE,
        'themes': list(settings.THEMES),
        'messages': {message: gettext(message) for message in MESSAGES},
    }


def _month(value: Any, fmt: str) -> str:
    """The value formatted as the `date` filter would in a template."""
    if isinstance(value, datetime.datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    return date_filter(value, fmt)


def stream_data(context: Context) -> dict[str, Any]:
    """StreamData in api-types.ts."""
    page = context.get('page') or {}
    return {
        'ctx': page.get('ctx', ''),
        'year_now': int(_month(timezone.now(), 'Y')),
        'view_date': _month(page.get('updated'), 'Y/m'),
        'archives': [_month(d, 'Y/m') for d in context.get('archives') or ()],
        'month_names': [_month(m, 'M')[:3] for m in page.get('months12', ())],
    }


@register.simple_tag(name='page_config')
def page_config_tag() -> SafeString:
    """The #gls-config script every page has."""
    return json_script(page_config(), 'gls-config')


@register.simple_tag(name='stream_data', takes_context=True)
def stream_data_tag(context: Context) -> SafeString:
    """The #gls-stream-data script of a stream page, for its archive calendar."""
    return json_script(stream_data(context), 'gls-stream-data')
