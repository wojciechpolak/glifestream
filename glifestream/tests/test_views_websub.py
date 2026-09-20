import hashlib
import hmac
import pytest
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from django.test import override_settings
from django.urls import reverse

from glifestream.apis.webfeed import WebfeedService
from glifestream.stream import websub
from glifestream.stream.models import WebSub
from glifestream.utils.time import now


@pytest.mark.django_db
def test_websub_dispatcher_verify(client, service):
    # Original urls.py uses [a-f0-9]{20} for websub
    h = 'a' * 20
    ws = WebSub.objects.create(hash=h, service=service, hub='http://hub.com')

    url = reverse('websub', kwargs={'id': ws.hash})
    # Verification GET request from Hub
    response = client.get(
        url,
        {
            'hub.mode': 'subscribe',
            'hub.challenge': 'hello-challenge',
            'hub.lease_seconds': '3600',
        },
    )

    assert response.status_code == 200
    assert response.content == b'hello-challenge'
    ws.refresh_from_db()
    assert ws.verified is True


@pytest.mark.django_db
def test_websub_dispatcher_post_content(client, service):
    h = 'b' * 20
    ws = WebSub.objects.create(
        hash=h, service=service, hub='http://hub.com', verified=True
    )

    url = reverse('websub', kwargs={'id': ws.hash})
    # Mock update POST. Patch websub.accept_payload which is what websub_dispatcher calls.
    with patch('glifestream.stream.websub.accept_payload', return_value=None):
        response = client.post(
            url, 'fake feed content', content_type='application/atom+xml'
        )

    assert response.status_code == 200


class HubError(IOError):
    """What a hub failure looks like to websub's error reporting."""

    def __init__(self, message=None, body=None, status_code=None):
        super().__init__(message or '')
        if message is not None:
            self.message = message
        if body is not None:
            self.read = lambda: body
        if status_code is not None:
            self.status_code = status_code


class FakeLink:
    def __init__(self, rel, href):
        self.rel = rel
        self.href = href


class FakeFeedApi(WebfeedService):
    """A WebfeedService whose run() just parks a parsed feed on the instance."""

    def __init__(self, links=(), fp_error=False):
        self.links = list(links)
        self.fp_error = fp_error
        self.fetch_only = False
        self.fp = SimpleNamespace(
            feed={'links': self.links}, bozo_exception='broken feed'
        )

    def run(self):
        return None


@contextmanager
def fake_service_api(api):
    with patch(
        'glifestream.apis.factory.ServiceFactory.create_service', return_value=api
    ):
        yield


@pytest.mark.django_db
def test_subscribe_rejects_an_api_without_websub_support(service):
    with fake_service_api(object()):
        result = websub.subscribe(service)

    assert result == {'rc': 1, 'error': 'WebSub is not supported by this API.'}


@pytest.mark.django_db
def test_subscribe_reports_a_feed_that_would_not_parse(service):
    with fake_service_api(FakeFeedApi(fp_error=True)):
        result = websub.subscribe(service)

    assert result == {'rc': 1, 'error': 'broken feed'}


@pytest.mark.django_db
def test_subscribe_reports_a_feed_without_a_hub(service):
    api = FakeFeedApi(links=[FakeLink('alternate', 'http://example.com/')])

    with fake_service_api(api):
        assert websub.subscribe(service) == {'rc': 2}


@pytest.mark.django_db
def test_subscribe_posts_to_the_hub_and_stores_the_subscription(service):
    api = FakeFeedApi(links=[FakeLink('hub', 'http://hub.example/')])

    with (
        fake_service_api(api),
        patch(
            'glifestream.utils.httpclient.post',
            return_value=SimpleNamespace(status_code=202),
        ) as post,
    ):
        result = websub.subscribe(service)

    assert result == {'hub': 'http://hub.example/', 'rc': 202}
    assert (
        WebSub.objects.filter(service=service, hub='http://hub.example/').count() == 1
    )

    data = post.call_args.kwargs['data']
    assert data['hub.mode'] == 'subscribe'
    assert data['hub.verify'] == 'async'
    assert data['hub.topic'].endswith('?format=atom')
    # A plain http hub gets no shared secret.
    assert 'hub.secret' not in data


@pytest.mark.django_db
def test_subscribe_sends_a_secret_to_an_https_hub(service):
    api = FakeFeedApi(links=[FakeLink('hub', 'https://hub.example/')])

    with (
        fake_service_api(api),
        patch(
            'glifestream.utils.httpclient.post',
            return_value=SimpleNamespace(status_code=202),
        ) as post,
    ):
        websub.subscribe(service)

    data = post.call_args.kwargs['data']
    assert len(data['hub.secret']) == 8
    assert WebSub.objects.get(service=service).secret.startswith(data['hub.secret'])


@pytest.mark.django_db
def test_subscribe_reuses_an_existing_subscription_row(service):
    api = FakeFeedApi(links=[FakeLink('hub', 'http://hub.example/')])

    with (
        fake_service_api(api),
        patch(
            'glifestream.utils.httpclient.post',
            return_value=SimpleNamespace(status_code=202),
        ),
    ):
        websub.subscribe(service)
        websub.subscribe(service)

    assert WebSub.objects.filter(service=service).count() == 1


@pytest.mark.django_db
def test_subscribe_returns_the_hub_error_text(service, capsys):
    api = FakeFeedApi(links=[FakeLink('hub', 'http://hub.example/')])
    failure = HubError(message='hub is down')

    with (
        fake_service_api(api),
        patch('glifestream.utils.httpclient.post', side_effect=failure),
    ):
        result = websub.subscribe(service, verbose=True)

    assert result == {'hub': 'http://hub.example/', 'rc': 'hub is down'}
    assert 'hub is down' in capsys.readouterr().out
    assert not WebSub.objects.filter(service=service).exists()


@pytest.mark.django_db
def test_unsubscribe_reports_a_missing_subscription():
    assert websub.unsubscribe(4242) == {'rc': 1}


@pytest.mark.django_db
def test_unsubscribe_posts_to_the_hub(service):
    ws = WebSub.objects.create(
        hash='c' * 20, service=service, hub='http://hub.example/'
    )

    with patch(
        'glifestream.utils.httpclient.post',
        return_value=SimpleNamespace(status_code=204),
    ) as post:
        result = websub.unsubscribe(ws.pk, verbose=True)

    assert result == {'hub': 'http://hub.example/', 'rc': 204}
    data = post.call_args.kwargs['data']
    assert data['hub.mode'] == 'unsubscribe'
    assert data['hub.verify'] == 'sync'


@pytest.mark.django_db
def test_unsubscribe_falls_back_to_the_response_body_for_an_error(service):
    ws = WebSub.objects.create(
        hash='d' * 20, service=service, hub='http://hub.example/'
    )
    failure = HubError(body='gone')

    with patch('glifestream.utils.httpclient.post', side_effect=failure):
        result = websub.unsubscribe(ws.pk)

    assert result == {'hub': 'http://hub.example/', 'rc': 'gone'}


@pytest.mark.django_db
def test_unsubscribe_tolerates_an_exception_with_nothing_to_say(service):
    ws = WebSub.objects.create(
        hash='e' * 20, service=service, hub='http://hub.example/'
    )

    with patch('glifestream.utils.httpclient.post', side_effect=HubError()):
        assert websub.unsubscribe(ws.pk) == {'hub': 'http://hub.example/', 'rc': ''}


@override_settings(BASE_URL='http://example.com')
@pytest.mark.django_db
def test_publish_pings_every_configured_hub(capsys):
    with patch(
        'glifestream.utils.httpclient.post',
        return_value=SimpleNamespace(status_code=204),
    ) as post:
        websub.publish(hubs=['http://hub.one/', 'http://hub.two/'], verbose=True)

    assert post.call_count == 2
    assert 'Successfully pinged' in capsys.readouterr().out


@override_settings(BASE_URL='http://example.com')
@pytest.mark.django_db
def test_publish_reports_an_unexpected_status(capsys):
    with patch(
        'glifestream.utils.httpclient.post',
        return_value=SimpleNamespace(status_code=500, content=b'nope'),
    ):
        websub.publish(hubs=['http://hub.one/'], verbose=True)

    assert 'Pinged and got 500' in capsys.readouterr().out


@override_settings(BASE_URL='http://localhost:8000')
@pytest.mark.django_db
def test_publish_does_nothing_from_a_local_install():
    with patch('glifestream.utils.httpclient.post') as post:
        websub.publish(hubs=['http://hub.one/'])

    post.assert_not_called()


@override_settings(BASE_URL='http://example.com')
@pytest.mark.django_db
def test_publish_treats_a_204_exception_as_success(capsys):
    failure = HubError(status_code=204)

    with patch('glifestream.utils.httpclient.post', side_effect=failure):
        websub.publish(hubs=['http://hub.one/'], verbose=True)

    assert capsys.readouterr().out == ''


@override_settings(BASE_URL='http://example.com')
@pytest.mark.django_db
def test_publish_reports_a_failed_ping(capsys):
    failure = HubError(message='unreachable')

    with patch('glifestream.utils.httpclient.post', side_effect=failure):
        websub.publish(hubs=['http://hub.one/'], verbose=True)

    assert 'unreachable' in capsys.readouterr().out


@pytest.mark.django_db
def test_verify_rejects_an_unknown_subscription():
    assert websub.verify('f' * 20, {'hub.mode': 'subscribe'}) is False
    assert websub.verify('f' * 20, {'hub.mode': 'unsubscribe'}) is False


@pytest.mark.django_db
def test_verify_removes_the_row_on_unsubscribe(service):
    ws = WebSub.objects.create(
        hash='1' * 20, service=service, hub='http://hub.example/'
    )

    result = websub.verify(ws.hash, {'hub.mode': 'unsubscribe', 'hub.challenge': 'ok'})

    assert result == 'ok'
    assert not WebSub.objects.filter(pk=ws.pk).exists()


@pytest.mark.django_db
def test_accept_payload_rejects_an_unknown_subscription():
    assert websub.accept_payload('2' * 20, b'body') is False


@pytest.mark.django_db
def test_accept_payload_rejects_a_bad_signature(service):
    WebSub.objects.create(
        hash='3' * 20, service=service, hub='http://hub.example/', secret='s3cret'
    )

    assert (
        websub.accept_payload(
            '3' * 20, b'body', {'HTTP_X_HUB_SIGNATURE': 'sha1=deadbeef'}
        )
        is False
    )


@pytest.mark.django_db
def test_accept_payload_runs_the_service_on_a_good_signature(service):
    secret = 's3cret'
    WebSub.objects.create(
        hash='4' * 20, service=service, hub='http://hub.example/', secret=secret
    )
    payload = b'<feed/>'
    signature = hmac.new(secret.encode('utf-8'), payload, hashlib.sha1).hexdigest()
    api = SimpleNamespace(payload=None, run=lambda: None)

    with fake_service_api(api):
        result = websub.accept_payload(
            '4' * 20, payload, {'HTTP_X_HUB_SIGNATURE': 'sha1=%s' % signature}
        )

    assert result is True
    assert api.payload == payload


@pytest.mark.django_db
def test_accept_payload_skips_verification_without_a_secret(service):
    WebSub.objects.create(
        hash='5' * 20, service=service, hub='http://hub.example/', secret=''
    )
    api = SimpleNamespace(payload=None, run=lambda: None)

    with fake_service_api(api):
        assert websub.accept_payload('5' * 20, b'anything') is True


@pytest.mark.django_db
def test_renew_subscriptions_only_renews_what_is_close_to_expiry(service):
    WebSub.objects.create(
        hash='6' * 20,
        service=service,
        hub='http://hub.example/',
        expire=now() + timedelta(days=30),
    )
    WebSub.objects.create(
        hash='7' * 20,
        service=service,
        hub='http://hub.example/',
        expire=now() + timedelta(days=1),
    )
    WebSub.objects.create(hash='8' * 20, service=service, hub='http://hub.example/')

    with patch('glifestream.stream.websub.subscribe') as subscribe:
        websub.renew_subscriptions()
    assert subscribe.call_count == 1

    with patch('glifestream.stream.websub.subscribe') as subscribe:
        websub.renew_subscriptions(force=True)
    assert subscribe.call_count == 2


@pytest.mark.django_db
def test_list_subs_prints_and_can_return_raw(service, capsys):
    WebSub.objects.create(hash='9' * 20, service=service, hub='http://hub.example/')

    assert websub.list_subs(raw=True).count() == 1

    websub.list_subs()
    assert 'hub=http://hub.example/' in capsys.readouterr().out
