import pytest
from unittest.mock import patch
from django.urls import reverse
from glifestream.stream.models import WebSub


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
