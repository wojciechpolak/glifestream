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

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from django.contrib.auth.models import User
from django.urls import reverse

from glifestream.stream.models import Service
from glifestream.usettings import oauth_settings


@pytest.fixture
def staff_client(client, db):
    User.objects.create_user(username='staff', password='password', is_staff=True)
    client.login(username='staff', password='password')
    return client


@pytest.fixture
def oauth_service(db):
    return Service.objects.create(name='Tweets', api='twitter', url='someone')


def oauth_url(service):
    return reverse('usettings-oauth', args=[service.pk])


def fake_client(phase=0, token='', with_urls=True):
    """A stand-in for gls_oauth.OAuth1Client with a settable phase."""
    c = MagicMock()
    c.db = SimpleNamespace(phase=phase, token=token)
    if with_urls:
        c.request_token_url = 'https://provider.example/request'
        c.authorize_url = 'https://provider.example/authorize'
        c.access_token_url = 'https://provider.example/access'
    else:
        c.request_token_url = None
        c.authorize_url = None
        c.access_token_url = None
    c.get_authorize_url.return_value = 'https://provider.example/authorize?token=abc'
    return c


@pytest.fixture
def patched_client():
    client = fake_client()

    with (
        patch(
            'glifestream.usettings.oauth_settings.gls_oauth.OAuth1Client',
            return_value=client,
        ),
        patch('glifestream.usettings.oauth_settings.ServiceFactory.create_service'),
    ):
        yield client


@pytest.mark.django_db
def test_oauth_refuses_a_non_staff_user(client, oauth_service):
    User.objects.create_user(username='plain', password='password', is_staff=False)
    client.login(username='plain', password='password')

    assert client.get(oauth_url(oauth_service)).status_code == 403


@pytest.mark.django_db
def test_oauth_renders_the_form(staff_client, oauth_service, patched_client):
    response = staff_client.get(oauth_url(oauth_service))

    assert response.status_code == 200
    assert response.context['phase'] == 0
    assert response.context['callback_url'].endswith(oauth_url(oauth_service))
    assert 'developer.twitter.com' in response.context['api_help']


@pytest.mark.django_db
def test_oauth_falls_back_to_generic_help_for_an_unknown_api(
    staff_client, patched_client
):
    service = Service.objects.create(name='Other', api='webfeed', url='x')

    response = staff_client.get(oauth_url(service))

    assert 'oauth.net' in response.context['api_help']


@pytest.mark.django_db
def test_oauth_asks_for_endpoints_a_provider_does_not_supply(
    staff_client, oauth_service, patched_client
):
    patched_client.request_token_url = None

    response = staff_client.get(oauth_url(oauth_service))

    assert response.context['page']['need_custom_urls'] is True
    assert response.context['v'] == {
        'request_token_url': '',
        'authorize_url': '',
        'access_token_url': '',
    }


@pytest.mark.django_db
def test_oauth_reset_clears_the_stored_credentials(
    staff_client, oauth_service, patched_client
):
    response = staff_client.post(oauth_url(oauth_service), {'reset': '1'})

    assert response.status_code == 200
    patched_client.reset.assert_called_once()
    patched_client.save.assert_called_once()


@pytest.mark.django_db
def test_oauth_post_requests_a_token_and_redirects_to_the_provider(
    staff_client, oauth_service, patched_client
):
    def advance():
        patched_client.db.phase = 1

    patched_client.get_request_token.side_effect = advance

    response = staff_client.post(
        oauth_url(oauth_service), {'identifier': 'key', 'secret': 'shh'}
    )

    assert response.status_code == 302
    assert response['Location'] == 'https://provider.example/authorize?token=abc'
    patched_client.save.assert_called_once()


@pytest.mark.django_db
def test_oauth_post_stores_operator_supplied_endpoints(
    staff_client, oauth_service, patched_client
):
    patched_client.request_token_url = None

    staff_client.post(
        oauth_url(oauth_service),
        {
            'request_token_url': 'https://custom.example/request',
            'authorize_url': 'https://custom.example/authorize',
            'access_token_url': 'https://custom.example/access',
        },
    )

    patched_client.set_urls.assert_called_once_with(
        'https://custom.example/request',
        'https://custom.example/authorize',
        'https://custom.example/access',
    )


@pytest.mark.django_db
def test_oauth_post_reports_a_provider_that_refuses_a_token(
    staff_client, oauth_service, patched_client
):
    patched_client.get_request_token.side_effect = Exception('provider said no')

    response = staff_client.post(oauth_url(oauth_service), {'identifier': 'key'})

    assert response.status_code == 200
    assert str(response.context['page']['msg']) == 'provider said no'


@pytest.mark.django_db
def test_oauth_get_accepts_the_providers_callback(
    staff_client, oauth_service, patched_client
):
    patched_client.db.phase = 1
    patched_client.db.token = 'expected-token'

    def advance():
        patched_client.db.phase = 3

    patched_client.get_access_token.side_effect = advance

    response = staff_client.get(
        oauth_url(oauth_service),
        {'oauth_token': 'expected-token', 'oauth_verifier': 'v1'},
    )

    assert response.status_code == 302
    assert response['Location'] == oauth_url(oauth_service)
    patched_client.consumer.parse_authorization_response.assert_called_once()
    assert patched_client.verifier == 'v1'


@pytest.mark.django_db
def test_oauth_get_ignores_a_callback_for_a_different_token(
    staff_client, oauth_service, patched_client
):
    patched_client.db.phase = 1
    patched_client.db.token = 'expected-token'

    response = staff_client.get(
        oauth_url(oauth_service), {'oauth_token': 'someone-else'}
    )

    assert response.status_code == 200
    patched_client.consumer.parse_authorization_response.assert_not_called()


@pytest.mark.django_db
def test_oauth_get_reports_a_failed_access_token_exchange(
    staff_client, oauth_service, patched_client
):
    patched_client.db.phase = 2
    patched_client.get_access_token.side_effect = Exception('exchange failed')

    response = staff_client.get(oauth_url(oauth_service))

    assert response.status_code == 200
    assert str(response.context['page']['msg']) == 'exchange failed'


def test_help_table_covers_twitter():
    assert 'twitter' in oauth_settings.OAUTH1_APIS_HELP
    assert oauth_settings.OAUTH1_DEFAULT_HELP.startswith('http')
