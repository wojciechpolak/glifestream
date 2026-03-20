from typing import Any, cast
import pytest
from unittest.mock import MagicMock, patch
from glifestream.gauth.gls_oauth import OAuth1Client


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
