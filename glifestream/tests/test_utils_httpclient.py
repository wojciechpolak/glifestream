from unittest.mock import patch, MagicMock, call

import pytest
import requests

from glifestream.utils import httpclient
from requests import Response


def _make_response(
    status_code: int,
    *,
    url: str = 'http://example.com/feed',
    reason: str = '',
    headers: dict[str, str] | None = None,
) -> MagicMock:
    response = MagicMock(spec=Response)
    response.status_code = status_code
    response.url = url
    response.reason = reason
    response.headers = headers or {}
    return response


@patch('requests.get')
def test_get_request(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.url = 'http://example.com'
    mock_get.return_value.headers = {}
    response = httpclient.get('example.com')
    assert response.status_code == 200
    mock_get.assert_called_once()
    # Check if http:// was prepended
    assert mock_get.call_args[0][0] == 'http://example.com'


@patch('requests.post')
def test_post_request(mock_post):
    mock_post.return_value.status_code = 201
    response = httpclient.post('example.com', data={'key': 'value'})
    assert response.status_code == 201
    mock_post.assert_called_once()


def test_get_alturl_if_html():
    mock_response = MagicMock(spec=Response)
    mock_response.headers = {'content-type': 'text/html; charset=UTF-8'}
    mock_response.text = '<html><head><link rel="alternate" type="application/rss+xml" href="/rss.xml"></head></html>'
    mock_response.url = 'http://example.com/'

    alt_url = httpclient.get_alturl_if_html(mock_response)
    assert alt_url == 'http://example.com/rss.xml'


@patch('glifestream.utils.httpclient.time.sleep')
@patch('requests.get')
def test_get_retries_timeout_then_succeeds(mock_get, mock_sleep):
    mock_get.side_effect = [
        requests.exceptions.Timeout('slow'),
        _make_response(200),
    ]

    response = httpclient.get('example.com')

    assert response.status_code == 200
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(1)


@patch('glifestream.utils.httpclient.time.sleep')
@patch('requests.get')
def test_get_retries_429_with_retry_after(mock_get, mock_sleep):
    mock_get.side_effect = [
        _make_response(
            429,
            reason='Too Many Requests',
            headers={'Retry-After': '7'},
        ),
        _make_response(200),
    ]

    response = httpclient.get('example.com')

    assert response.status_code == 200
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(7)


@patch('glifestream.utils.httpclient.time.sleep')
@patch('requests.get')
def test_get_retries_503_with_backoff(mock_get, mock_sleep):
    mock_get.side_effect = [
        _make_response(503, reason='Service Unavailable'),
        _make_response(503, reason='Service Unavailable'),
        _make_response(200),
    ]

    response = httpclient.get('example.com')

    assert response.status_code == 200
    assert mock_get.call_count == 3
    assert mock_sleep.mock_calls == [call(1), call(2)]


@patch('glifestream.utils.httpclient.time.sleep')
@patch('requests.get')
def test_get_connection_error_retries_then_raises(mock_get, mock_sleep):
    mock_get.side_effect = requests.exceptions.ConnectionError('offline')

    with pytest.raises(httpclient.FetchError) as excinfo:
        httpclient.get('example.com')

    assert excinfo.value.category == 'connection'
    assert excinfo.value.retryable is True
    assert mock_get.call_count == 3
    assert mock_sleep.mock_calls == [call(1), call(2)]


@patch('glifestream.utils.httpclient.time.sleep')
@patch('requests.get')
def test_get_401_is_not_retried(mock_get, mock_sleep):
    mock_get.return_value = _make_response(401, reason='Unauthorized')

    with pytest.raises(httpclient.FetchError) as excinfo:
        httpclient.get('example.com')

    assert excinfo.value.category == 'auth'
    assert excinfo.value.retryable is False
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


@patch('glifestream.utils.httpclient.time.sleep')
@patch('requests.get')
def test_get_404_is_not_retried(mock_get, mock_sleep):
    mock_get.return_value = _make_response(404, reason='Not Found')

    with pytest.raises(httpclient.FetchError) as excinfo:
        httpclient.get('example.com')

    assert excinfo.value.category == 'remote_4xx'
    assert excinfo.value.retryable is False
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


@patch('requests.post')
def test_post_timeout_is_not_retried(mock_post):
    mock_post.side_effect = requests.exceptions.Timeout('slow')

    with pytest.raises(httpclient.FetchError) as excinfo:
        httpclient.post('example.com', data={'key': 'value'})

    assert excinfo.value.category == 'timeout'
    mock_post.assert_called_once()


def test_require_json_wraps_invalid_response():
    response = _make_response(200)
    response.json.side_effect = ValueError('bad json')

    with pytest.raises(httpclient.FetchError) as excinfo:
        httpclient.require_json(response)

    assert excinfo.value.category == 'invalid_response'
    assert 'bad json' in excinfo.value.detail


def test_gen_auth():
    from glifestream.stream.models import Service

    service = Service(creds='user:pass')
    assert httpclient.gen_auth(service) == ['user', 'pass']

    service_none = Service(creds='')
    assert httpclient.gen_auth(service_none) is None
