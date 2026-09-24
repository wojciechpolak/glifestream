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

The JSON the page script reads, field by field.

frontend/src/api-types.ts declares these payloads for the TypeScript code.
Each test here checks that a view still sends every field that file lists,
with the type it declares. A field renamed or dropped on one side fails
here, so change the two files together.
"""

from __future__ import annotations

import datetime
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from django.urls import reverse

from glifestream.stream.models import Entry, Service
from glifestream.stream.templatetags.gls_page import MESSAGES

FRONTEND_SRC = Path(__file__).parents[2] / 'frontend' / 'src'

NoneType = type(None)

# FetchState in api-types.ts. Optional fields are listed; the views send all.
FETCH_STATE = {
    'service_id': int,
    'status': str,
    'requested_at': (str, NoneType),
    'started_at': (str, NoneType),
    'finished_at': (str, NoneType),
    'last_succeeded_at': (str, NoneType),
    'last_failed_at': (str, NoneType),
    'next_fetch_at': (str, NoneType),
    'last_result': str,
    'last_error': str,
    'failure_note': str,
}

FETCH_STATUSES = {'idle', 'queued', 'running', 'succeeded', 'failed'}

# PageConfig and StreamData in api-types.ts.
PAGE_CONFIG = {'baseurl': str, 'maps_engine': str, 'themes': list, 'messages': dict}
STREAM_DATA = {
    'ctx': str,
    'year_now': int,
    'view_date': str,
    'archives': list,
    'month_names': list,
}

# ServiceForm and ServiceFormField in api-types.ts.
SERVICE_FORM = {
    'api': str,
    'name': str,
    'action': str,
    'method': str,
    'fields': list,
    'save': str,
    'cancel': str,
}
SERVICE_FORM_OPTIONAL = {
    'id': (int, NoneType),
    'delete': str,
    'need_import': bool,
    'fetch_status': dict,
}
FIELD = {'type': str, 'name': str, 'label': str}
FIELD_OPTIONAL = {
    'value': (str, int),
    'placeholder': str,
    'hint': str,
    'miss': bool,
    'checked': bool,
    'href': str,
    'options': list,
    'deps': dict,
}
FIELD_TYPES = {'text', 'number', 'password', 'select', 'checkbox', 'link'}


def assert_fields(
    payload: dict[str, Any],
    required: dict[str, Any],
    optional: dict[str, Any] | None = None,
) -> None:
    """`payload` has every required field, and each field has its type."""
    missing = required.keys() - payload.keys()
    assert not missing, f'missing {sorted(missing)} in {payload}'
    for name, kind in {**required, **(optional or {})}.items():
        if name in payload:
            assert isinstance(payload[name], kind), (name, payload[name])


def assert_fetch_state(state: dict[str, Any]) -> None:
    assert_fields(state, FETCH_STATE)
    assert state['status'] in FETCH_STATUSES


def assert_service_form(form: dict[str, Any]) -> None:
    assert_fields(form, SERVICE_FORM, SERVICE_FORM_OPTIONAL)
    assert form['method'] in ('get', 'post')
    for field in form['fields']:
        assert_fields(field, FIELD, FIELD_OPTIONAL)
        assert field['type'] in FIELD_TYPES
        if field['type'] == 'select':
            for option in field['options']:
                assert [type(part) for part in option] == [str, str], option
        for controlling, value in field.get('deps', {}).items():
            assert isinstance(controlling, str) and isinstance(value, str)
    if 'fetch_status' in form:
        assert_fetch_state(form['fetch_status'])


class _JsonScripts(HTMLParser):
    """The json_script elements of a page, by id."""

    def __init__(self) -> None:
        super().__init__()
        self.found: dict[str, Any] = {}
        self._id: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == 'script' and values.get('type') == 'application/json':
            self._id = values.get('id')

    def handle_data(self, data: str) -> None:
        if self._id:
            self.found[self._id] = json.loads(data)
            self._id = None


def json_scripts(html: str) -> dict[str, Any]:
    parser = _JsonScripts()
    parser.feed(html)
    return parser.found


def settings_api(cmd: str) -> str:
    return reverse('usettings-api-cmd', args=[cmd])


@pytest.fixture
def staff_client(client, django_user_model):
    django_user_model.objects.create_user(
        username='staff', password='password', is_staff=True
    )
    client.login(username='staff', password='password')
    return client


@pytest.mark.django_db
def test_gsc_sends_selfposts_classes(admin_client):
    Service.objects.create(name='Notes', api='selfposts', cls='notes', url='')

    response = admin_client.post(reverse('api', kwargs={'cmd': 'gsc'}))

    # SelfpostsClass[]
    [item] = response.json()
    assert_fields(item, {'id': int, 'cls': str})


@pytest.mark.django_db
def test_html_pure_page_sends_entries_and_the_next_page(client, service, settings):
    settings.ENTRIES_ON_PAGE = 1
    for n in range(2):
        Entry.objects.create(
            service=service,
            title=f'Entry {n}',
            guid=f'contract-{n}',
            link='http://example.com/',
            date_published=datetime.datetime(2025, 1, 1 + n, tzinfo=datetime.UTC),
        )

    response = client.get(
        reverse('index'),
        {'format': 'html-pure'},
        headers={'x-requested-with': 'XMLHttpRequest'},
    )

    # StreamPage
    page = response.json()
    assert_fields(page, {'stream': str, 'next': (str, int)})
    assert 'Entry 1' in page['stream']
    assert page['next']


@pytest.mark.django_db
def test_every_page_sends_its_config(client, settings):
    settings.MAPS_ENGINE = 'google'
    settings.THEMES = ('default', 'dark')

    for url in (reverse('index'), reverse('login')):
        config = json_scripts(client.get(url).text)['gls-config']

        # PageConfig
        assert_fields(config, PAGE_CONFIG)
        assert config['baseurl'] == reverse('index')
        assert config['maps_engine'] == 'google'
        assert config['themes'] == ['default', 'dark']
        assert config['messages']['Undo'] == 'Undo'


@pytest.mark.django_db
def test_page_config_translates_the_messages(client):
    config = json_scripts(client.get(reverse('index'), HTTP_ACCEPT_LANGUAGE='pl').text)

    assert config['gls-config']['messages']['Undo'] == 'Cofnij'


def test_page_config_lists_every_message_the_page_script_translates():
    used = set()
    for source in FRONTEND_SRC.rglob('*.ts'):
        if not source.name.endswith('.test.ts'):
            used |= set(
                re.findall(r"\b(?:_|gettext)\(\s*'([^']*)'", source.read_text())
            )

    assert used == set(MESSAGES)


@pytest.mark.django_db
def test_stream_page_sends_its_calendar_data(client, service):
    for day in (datetime.datetime(2025, 3, 1), datetime.datetime(2025, 11, 5)):
        Entry.objects.create(
            service=service,
            title='Entry',
            guid=f'calendar-{day:%m}',
            link='http://example.com/',
            date_published=day.replace(tzinfo=datetime.UTC),
        )

    response = client.get(reverse('index'))

    # StreamData
    data = json_scripts(response.text)['gls-stream-data']
    assert_fields(data, STREAM_DATA)
    assert data['ctx'] == ''
    assert data['year_now'] == datetime.date.today().year
    assert data['view_date'] == '2025/11'
    assert data['archives'] == ['2025/11', '2025/03']
    assert data['month_names'][0] == 'Jan' and len(data['month_names']) == 12


@pytest.mark.django_db
def test_service_form_for_a_new_service(staff_client):
    response = staff_client.post(
        settings_api('service'), {'method': 'get', 'api': 'webfeed'}
    )

    form = response.json()
    assert_service_form(form)
    assert {field['type'] for field in form['fields']} >= {
        'text',
        'number',
        'select',
        'checkbox',
    }


@pytest.mark.django_db
def test_service_form_after_saving_a_service(staff_client):
    response = staff_client.post(
        settings_api('service'),
        {
            'method': 'post',
            'api': 'mastodon',
            'name': 'Toots',
            'url': 'https://mastodon.example/@me',
            'user_id': 'me',
            'timeline': 'user',
            'auth': 'oauth2',
        },
    )

    form = response.json()
    assert_service_form(form)
    assert form['method'] == 'post'
    assert isinstance(form['id'], int)
    assert 'delete' in form and 'fetch_status' in form and 'need_import' in form
    fields = {field['name']: field for field in form['fields']}
    assert fields['oauth2_conf']['type'] == 'link'
    assert fields['url']['deps'] == {'timeline': 'user'}


@pytest.mark.django_db
def test_service_form_marks_a_missing_field(staff_client):
    response = staff_client.post(
        settings_api('service'), {'method': 'post', 'api': 'webfeed', 'name': ''}
    )

    form = response.json()
    assert_service_form(form)
    missing = [field['name'] for field in form['fields'] if field.get('miss')]
    assert missing


@pytest.mark.django_db
def test_fetch_status_sends_each_service_state(staff_client):
    service = Service.objects.create(name='Feed', api='webfeed', url='http://f.com')

    response = staff_client.get(settings_api('fetch-status'))

    # FetchStatusResponse
    services = response.json()['services']
    assert list(services) == [str(service.pk)]
    assert_fetch_state(services[str(service.pk)])


@pytest.mark.django_db
@pytest.mark.parametrize('cmd', ['fetch-now', 'import'])
def test_fetch_now_sends_the_new_state(staff_client, cmd):
    service = Service.objects.create(name='Feed', api='webfeed', url='http://f.com')

    with patch('glifestream.fetching.send_worker_wake_signal', return_value=True):
        response = staff_client.post(settings_api(cmd), {'id': service.pk})

    # FetchNowResponse
    assert_fetch_state(response.json()['state'])


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('api', 'status'), [('selfposts', 400), (None, 404)], ids=['refused', 'missing']
)
def test_fetch_now_explains_a_refusal(staff_client, api, status):
    service_id = 999999
    if api:
        service_id = Service.objects.create(name='Notes', api=api, url='').pk

    response = staff_client.post(settings_api('fetch-now'), {'id': service_id})

    # FetchNowError
    assert response.status_code == status
    assert_fields(response.json(), {'error': str})
