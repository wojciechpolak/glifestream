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


def _oauth1_client(service, **kwargs) -> OAuth1Client:
    mock_api = MagicMock()
    mock_api.OAUTH_REQUEST_TOKEN_URL = 'http://test/request'
    mock_api.OAUTH_AUTHORIZE_URL = 'http://test/authorize'
    mock_api.OAUTH_ACCESS_TOKEN_URL = 'http://test/access'
    with patch('glifestream.gauth.gls_oauth.OAuth1Session'):
        return OAuth1Client(service, mock_api, **kwargs)


@pytest.mark.django_db
def test_oauth1_new_client_takes_the_given_credentials(service):
    client = _oauth1_client(service, identifier='key', secret='shh')
    assert (client.db.identifier, client.db.secret) == ('key', 'shh')


@pytest.mark.django_db
def test_oauth1_get_request_token_rejects_a_response_without_tokens(service):
    client = _oauth1_client(service)
    cast(Any, client.consumer).fetch_request_token.return_value = {}

    with pytest.raises(Exception, match='No tokens found'):
        client.get_request_token()
    assert client.db.phase == 0


@pytest.mark.django_db
def test_oauth1_get_request_token_needs_a_url(service):
    client = _oauth1_client(service)
    client.set_urls()
    with pytest.raises(Exception, match='Request token URL not set'):
        client.get_request_token()


@pytest.mark.django_db
def test_oauth1_get_authorize_url(service):
    client = _oauth1_client(service)
    consumer = cast(Any, client.consumer)
    consumer.authorization_url.return_value = 'http://test/authorize?t=1'

    with pytest.raises(Exception, match='Not ready to authorize'):
        client.get_authorize_url()

    client.db.phase = 1
    assert client.get_authorize_url() == 'http://test/authorize?t=1'
    consumer.authorization_url.assert_called_once_with('http://test/authorize')

    client.set_urls(request_token_url='http://test/request')
    with pytest.raises(Exception, match='Authorize URL not set'):
        client.get_authorize_url()


@pytest.mark.django_db
def test_oauth1_get_access_token_completes_the_flow(service):
    client = _oauth1_client(service)
    consumer = cast(Any, client.consumer)
    response = {'oauth_token': 'tok', 'oauth_token_secret': 'sec'}
    consumer.fetch_access_token.return_value = response

    with pytest.raises(Exception, match='Not ready to get access token'):
        client.get_access_token()

    client.db.phase = 2
    client.get_access_token()

    consumer.fetch_access_token.assert_called_once_with('http://test/access')
    assert (client.db.phase, client.db.token, client.db.token_secret) == (
        3,
        'tok',
        'sec',
    )
    assert client.content == response


@pytest.mark.django_db
def test_oauth1_get_access_token_failures(service):
    client = _oauth1_client(service)
    client.db.phase = 2
    cast(Any, client.consumer).fetch_access_token.return_value = {'oauth_token': 't'}

    with pytest.raises(Exception, match='No tokens found'):
        client.get_access_token()
    assert client.db.phase == 2

    client.set_urls()
    with pytest.raises(Exception, match='Access token URL not set'):
        client.get_access_token()


@pytest.mark.django_db
def test_oauth1_reset_forgets_tokens(service):
    client = _oauth1_client(service)
    client.db.phase, client.db.token, client.db.token_secret = 3, 't', 's'

    client.reset()

    assert (client.db.phase, client.db.token, client.db.token_secret) == (
        0,
        None,
        None,
    )
