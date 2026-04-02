from typing import Any, cast
import pytest
from unittest.mock import MagicMock, patch
from glifestream.gauth.gls_oauth import OAuth1Client
from glifestream.gauth.gls_oauth2 import OAuth2Client, PHASE_0, PHASE_2, PHASE_3


@pytest.mark.django_db
def test_oauth1_client_init(service):
    with patch('glifestream.gauth.gls_oauth.OAuth1Session'):
        mock_api = MagicMock()
        mock_api.OAUTH_REQUEST_TOKEN_URL = 'http://test/request'

        client = OAuth1Client(service, mock_api)
        assert client.request_token_url == 'http://test/request'


@pytest.mark.django_db
def test_oauth1_get_request_token(service):
    with patch('glifestream.gauth.gls_oauth.OAuth1Session'):
        mock_api = MagicMock()
        mock_api.OAUTH_REQUEST_TOKEN_URL = 'http://test/request'

        client = OAuth1Client(service, mock_api)
        consumer = cast(Any, client.consumer)
        consumer.fetch_request_token.return_value = {
            'oauth_token': 'token',
            'oauth_token_secret': 'secret',
        }

        client.get_request_token()
        assert client.db.token == 'token'
        assert client.db.phase == 1


@pytest.mark.django_db
def test_oauth2_client_init_with_identifier_and_secret(service):
    mock_consumer = MagicMock()
    mock_consumer.headers = {}
    mock_api = MagicMock()
    mock_api.get_base_url.return_value = 'https://example.social'
    mock_api.get_authorize_url.return_value = 'https://example.social/oauth/authorize'
    mock_api.get_token_url.return_value = 'https://example.social/oauth/token'

    with patch(
        'glifestream.gauth.gls_oauth2.OAuth2Session', return_value=mock_consumer
    ) as mock_session:
        client = OAuth2Client(
            service,
            mock_api,
            identifier='client-id',
            secret='client-secret',
            callback_url='https://app.example.test/callback',
        )

    mock_session.assert_called_once_with(
        client_id='client-id',
        redirect_uri='https://app.example.test/callback',
        scope=['read'],
        token=None,
    )
    assert client.db.identifier == 'client-id'
    assert client.db.secret == 'client-secret'
    assert client.base_url == 'https://example.social'
    assert client.authorize_url == 'https://example.social/oauth/authorize'
    assert client.token_url == 'https://example.social/oauth/token'
    assert mock_consumer.headers['User-Agent']


@pytest.mark.django_db
def test_oauth2_get_authorize_url(service):
    mock_consumer = MagicMock()
    mock_consumer.headers = {}
    mock_consumer.authorization_url.return_value = (
        'https://example.social/oauth/authorize?state=test',
        'state-test',
    )
    mock_api = MagicMock()
    mock_api.get_base_url.return_value = 'https://example.social'
    mock_api.get_authorize_url.return_value = 'https://example.social/oauth/authorize'
    mock_api.get_token_url.return_value = 'https://example.social/oauth/token'

    with patch(
        'glifestream.gauth.gls_oauth2.OAuth2Session', return_value=mock_consumer
    ):
        client = OAuth2Client(
            service,
            mock_api,
            identifier='client-id',
            secret='client-secret',
            callback_url='https://app.example.test/callback',
        )

    client.db.phase = PHASE_0
    url = client.get_authorize_url()

    assert url == 'https://example.social/oauth/authorize?state=test'
    mock_consumer.authorization_url.assert_called_once_with(
        'https://example.social/oauth/authorize'
    )


@pytest.mark.django_db
def test_oauth2_get_access_token_sets_phase_and_token(service):
    mock_consumer = MagicMock()
    mock_consumer.headers = {}
    mock_consumer.fetch_token.return_value = {'access_token': 'access-token'}
    mock_api = MagicMock()
    mock_api.get_base_url.return_value = 'https://example.social'
    mock_api.get_authorize_url.return_value = 'https://example.social/oauth/authorize'
    mock_api.get_token_url.return_value = 'https://example.social/oauth/token'

    with patch(
        'glifestream.gauth.gls_oauth2.OAuth2Session', return_value=mock_consumer
    ):
        client = OAuth2Client(
            service,
            mock_api,
            identifier='client-id',
            secret='client-secret',
            callback_url='https://app.example.test/callback',
        )

    client.db.phase = PHASE_2
    client.get_access_token('auth-code')

    mock_consumer.fetch_token.assert_called_once_with(
        token_url='https://example.social/oauth/token',
        code='auth-code',
        client_secret='client-secret',
    )
    assert client.db.phase == PHASE_3
    assert client.db.token == 'access-token'
    assert client.content == {'access_token': 'access-token'}


@pytest.mark.django_db
def test_oauth2_get_access_token_requires_access_token_in_response(service):
    mock_consumer = MagicMock()
    mock_consumer.headers = {}
    mock_consumer.fetch_token.return_value = {'token_type': 'Bearer'}
    mock_api = MagicMock()
    mock_api.get_base_url.return_value = 'https://example.social'
    mock_api.get_authorize_url.return_value = 'https://example.social/oauth/authorize'
    mock_api.get_token_url.return_value = 'https://example.social/oauth/token'

    with patch(
        'glifestream.gauth.gls_oauth2.OAuth2Session', return_value=mock_consumer
    ):
        client = OAuth2Client(
            service,
            mock_api,
            identifier='client-id',
            secret='client-secret',
            callback_url='https://app.example.test/callback',
        )

    client.db.phase = PHASE_2

    with pytest.raises(Exception, match='No access token found'):
        client.get_access_token('auth-code')
