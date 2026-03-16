import pytest
import datetime
from django.urls import reverse
from django.contrib.auth.models import User
from glifestream.stream.models import Entry, Favorite

UTC = datetime.timezone.utc


@pytest.fixture(autouse=True)
def system_tz():
    import os
    import time

    old_tz = os.environ.get('TZ')
    os.environ['TZ'] = 'UTC'
    time.tzset()
    yield
    if old_tz:
        os.environ['TZ'] = old_tz
    else:
        del os.environ['TZ']
    time.tzset()


@pytest.mark.django_db
def test_index_page(client):
    url = reverse('index')
    response = client.get(url)
    assert response.status_code == 200
    assert 'entries' in response.context


@pytest.fixture
def entry(db, service):
    return Entry.objects.create(
        service=service,
        title='Test Entry',
        guid='api-test',
        link='http://test.com',
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )


@pytest.mark.django_db
def test_api_hide_unhide(admin_client, entry):
    url = reverse('api', kwargs={'cmd': 'hide'})
    response = admin_client.post(url, {'entry': entry.id})
    assert response.status_code == 200
    entry.refresh_from_db()
    assert entry.active is False

    url = reverse('api', kwargs={'cmd': 'unhide'})
    response = admin_client.post(url, {'entry': entry.id})
    assert response.status_code == 200
    entry.refresh_from_db()
    assert entry.active is True


@pytest.mark.django_db
def test_api_favorite_unfavorite(admin_client, user, entry):
    # Favorite
    url = reverse('api', kwargs={'cmd': 'favorite'})
    response = admin_client.post(url, {'entry': entry.id})
    assert response.status_code == 200
    # Note: admin_client is an admin user, but the command uses request.user
    # Need to check if a favorite was created for the logged in user
    admin_user = User.objects.get(username='admin')
    assert Favorite.objects.filter(user=admin_user, entry=entry).exists()

    # Unfavorite
    url = reverse('api', kwargs={'cmd': 'unfavorite'})
    response = admin_client.post(url, {'entry': entry.id})
    assert response.status_code == 200
    assert not Favorite.objects.filter(user=admin_user, entry=entry).exists()


@pytest.mark.django_db
def test_api_getcontent_public(client, service):
    entry = Entry.objects.create(
        service=service,
        title='Public',
        guid='p1',
        link='http://p.com',
        content='Secret Content',
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )
    # Service must be public for 'getcontent' to work for unauth users
    service.public = True
    service.save()

    url = reverse('api', kwargs={'cmd': 'getcontent'})
    response = client.post(url, {'entry': entry.id})
    assert response.status_code == 200
    assert 'Secret Content' in response.content.decode()


@pytest.mark.django_db
def test_api_putcontent_forbidden_for_anonymous(client, entry):
    url = reverse('api', kwargs={'cmd': 'putcontent'})
    response = client.post(url, {'entry': entry.id, 'content': 'new'})
    assert response.status_code == 403
