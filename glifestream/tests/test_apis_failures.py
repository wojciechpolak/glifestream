"""How each provider's fetch fails, as the worker sees it.

The worker schedules the next attempt from the `FetchError` that leaves a
provider's `run()`: retry soon for a flaky remote, wait long for one that
rejects credentials or sends a payload retrying cannot fix. These tests put
every provider through the same failures and check that the error comes out
classified, instead of being swallowed or reported as unexpected. The HTTP
providers are driven through the real `httpclient`, mocked only at
`requests.get`.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
from atproto_client import exceptions as atproto_errors
from atproto_client.models.common import XrpcError
from atproto_client.request import Response as XrpcResponse

from glifestream.apis.factory import ServiceFactory
from glifestream.fetching import classify_fetch_failure
from glifestream.stream.models import Entry, Service, ServiceFetchState
from glifestream.utils import httpclient

RETRYABLE = ServiceFetchState.FAILURE_RETRYABLE
TERMINAL = ServiceFetchState.FAILURE_TERMINAL

FEED_PROVIDERS = {
    'webfeed': {'url': 'https://remote.example/feed'},
    'flickr': {'url': '12345@N00'},
}
JSON_PROVIDERS = {
    'mastodon': {'url': 'https://remote.example', 'user_id': '1'},
    'pixelfed': {'url': 'https://remote.example', 'user_id': '1'},
    'youtube': {'url': 'https://remote.example/playlist'},
    'vimeo': {'url': 'someone'},
}
HTTP_PROVIDERS = {**FEED_PROVIDERS, **JSON_PROVIDERS}


def http_response(
    status_code: int,
    body: bytes = b'',
    *,
    content_type: str = 'application/json',
) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.headers['content-type'] = content_type
    response.url = 'https://remote.example/'
    response.raw = io.BytesIO(body)
    return response


def make_service(api: str, **fields: Any) -> Service:
    return Service.objects.create(
        api=api, name=api, active=True, creds='handle:secret', **fields
    )


def fetch_error(service: Service, *, answer: Any) -> httpclient.FetchError:
    """Run `service`'s provider against a remote that gives `answer`.

    `answer` is the response every request gets, or the exception it raises.
    """
    get = MagicMock()
    if isinstance(answer, BaseException):
        get.side_effect = answer
    else:
        get.return_value = answer
    with (
        patch('glifestream.utils.httpclient.requests.get', get),
        patch('glifestream.utils.httpclient.time.sleep'),
        pytest.raises(httpclient.FetchError) as raised,
    ):
        ServiceFactory.create_service(service).run()
    assert get.called
    return raised.value


def assert_failed_cleanly(service: Service) -> None:
    """A failed fetch must not look like a check, nor store half an import."""
    service.refresh_from_db()
    assert service.last_checked is None
    assert not Entry.objects.filter(service=service).exists()


@pytest.mark.django_db
@pytest.mark.parametrize('api', HTTP_PROVIDERS)
@pytest.mark.parametrize(
    'status_code, category, kind',
    [
        (401, 'auth', TERMINAL),
        (404, 'remote_4xx', TERMINAL),
        (429, 'rate_limited', RETRYABLE),
        (503, 'remote_5xx', RETRYABLE),
    ],
)
def test_http_error_status_is_classified(api, status_code, category, kind):
    service = make_service(api, **HTTP_PROVIDERS[api])

    error = fetch_error(service, answer=http_response(status_code))

    assert (error.category, error.status_code) == (category, status_code)
    assert classify_fetch_failure(error).kind == kind
    assert_failed_cleanly(service)


@pytest.mark.django_db
@pytest.mark.parametrize('api', HTTP_PROVIDERS)
@pytest.mark.parametrize(
    'exception, category',
    [
        (requests.exceptions.ConnectTimeout('slow'), 'timeout'),
        (requests.exceptions.ConnectionError('refused'), 'connection'),
    ],
)
def test_unreachable_remote_is_retried(api, exception, category):
    service = make_service(api, **HTTP_PROVIDERS[api])

    error = fetch_error(service, answer=exception)

    assert error.category == category
    assert classify_fetch_failure(error).kind == RETRYABLE
    assert_failed_cleanly(service)


@pytest.mark.django_db
@pytest.mark.parametrize('api', FEED_PROVIDERS)
def test_malformed_feed_is_not_retried(api):
    service = make_service(api, **FEED_PROVIDERS[api])
    broken = http_response(
        200, b'<rss><channel><item><title>cut', content_type='application/rss+xml'
    )

    error = fetch_error(service, answer=broken)

    assert error.category == 'parse_error'
    assert classify_fetch_failure(error).kind == TERMINAL
    assert_failed_cleanly(service)


@pytest.mark.django_db
@pytest.mark.parametrize('api', FEED_PROVIDERS)
def test_html_page_without_a_feed_is_not_retried(api):
    service = make_service(api, **FEED_PROVIDERS[api])
    page = http_response(200, b'<html><body>Hi</body></html>', content_type='text/html')

    error = fetch_error(service, answer=page)

    assert error.category == 'invalid_response'
    assert classify_fetch_failure(error).kind == TERMINAL
    assert_failed_cleanly(service)


@pytest.mark.django_db
@pytest.mark.parametrize('api', JSON_PROVIDERS)
def test_non_json_payload_is_not_retried(api):
    service = make_service(api, **JSON_PROVIDERS[api])
    page = http_response(200, b'<html>Maintenance</html>', content_type='text/html')

    error = fetch_error(service, answer=page)

    assert error.category == 'invalid_response'
    assert classify_fetch_failure(error).kind == TERMINAL
    assert_failed_cleanly(service)


def xrpc_response(status_code: int, error: str = 'Error') -> XrpcResponse:
    return XrpcResponse(
        success=False,
        status_code=status_code,
        content=XrpcError(error=error, message='from the PDS'),
        headers={},
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    'exception, category, kind',
    [
        (atproto_errors.UnauthorizedError(xrpc_response(401)), 'auth', TERMINAL),
        (atproto_errors.LoginRequiredError(), 'auth', TERMINAL),
        (atproto_errors.BadRequestError(xrpc_response(400)), 'remote_4xx', TERMINAL),
        (
            atproto_errors.RequestException(xrpc_response(429, 'RateLimitExceeded')),
            'rate_limited',
            RETRYABLE,
        ),
        (atproto_errors.NetworkError(xrpc_response(502)), 'remote_5xx', RETRYABLE),
        (atproto_errors.NetworkError(), 'connection', RETRYABLE),
        (atproto_errors.InvokeTimeoutError(), 'timeout', RETRYABLE),
        (atproto_errors.ModelError('bad record'), 'invalid_response', TERMINAL),
    ],
)
def test_atproto_client_error_is_classified(exception, category, kind):
    service = make_service('atproto')
    client = MagicMock()
    client.get_timeline.side_effect = exception

    with (
        patch('glifestream.apis.atproto.Client', return_value=client),
        pytest.raises(httpclient.FetchError) as raised,
    ):
        ServiceFactory.create_service(service).run()

    assert raised.value.category == category
    assert classify_fetch_failure(raised.value).kind == kind
    assert raised.value.__cause__ is exception
    assert not Entry.objects.filter(service=service).exists()


@pytest.mark.django_db
def test_atproto_without_credentials_is_an_auth_failure():
    service = make_service('atproto')
    service.creds = ''
    service.save()
    client = MagicMock()

    with (
        patch('glifestream.apis.atproto.Client', return_value=client),
        pytest.raises(httpclient.FetchError) as raised,
    ):
        ServiceFactory.create_service(service).run()

    assert raised.value.category == 'auth'
    assert classify_fetch_failure(raised.value).kind == TERMINAL
    client.login.assert_not_called()


@pytest.mark.django_db
def test_atproto_bug_is_reported_as_unexpected():
    service = make_service('atproto')
    client = MagicMock()
    client.get_timeline.side_effect = KeyError('feed')

    with (
        patch('glifestream.apis.atproto.Client', return_value=client),
        pytest.raises(KeyError),
    ):
        ServiceFactory.create_service(service).run()


@pytest.mark.django_db
@pytest.mark.parametrize('api', ['twitter', 'pocket', 'friendfeed'])
def test_defunct_provider_fetches_nothing(api):
    service = make_service(api, url='someone')

    with patch('glifestream.utils.httpclient.requests.get') as get:
        ServiceFactory.create_service(service).run()

    get.assert_not_called()
    assert_failed_cleanly(service)
