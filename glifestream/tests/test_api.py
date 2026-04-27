import pytest
import datetime
from urllib.parse import quote
from django.conf import settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.test import override_settings
from glifestream.stream.models import Entry, Favorite
from glifestream.testsupport.magic_sso import make_magic_sso_token

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
    response = admin_client.post(url, {'entry': entry.pk})
    assert response.status_code == 200
    entry.refresh_from_db()
    assert entry.active is False

    url = reverse('api', kwargs={'cmd': 'unhide'})
    response = admin_client.post(url, {'entry': entry.pk})
    assert response.status_code == 200
    entry.refresh_from_db()
    assert entry.active is True


@pytest.mark.django_db
def test_api_favorite_unfavorite(admin_client, user, entry):
    # Favorite
    url = reverse('api', kwargs={'cmd': 'favorite'})
    response = admin_client.post(url, {'entry': entry.pk})
    assert response.status_code == 200
    # Note: admin_client is an admin user, but the command uses request.user
    # Need to check if a favorite was created for the logged in user
    admin_user = User.objects.get(username='admin')
    assert Favorite.objects.filter(user=admin_user, entry=entry).exists()

    # Unfavorite
    url = reverse('api', kwargs={'cmd': 'unfavorite'})
    response = admin_client.post(url, {'entry': entry.pk})
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
    response = client.post(url, {'entry': entry.pk})
    assert response.status_code == 200
    assert 'Secret Content' in response.content.decode()


@override_settings(MAGICSSO_ENABLED=False)
@pytest.mark.django_db
def test_api_getcontent_hides_friends_only_entry_for_anonymous(client, service):
    entry = Entry.objects.create(
        service=service,
        title='Friends',
        guid='fo-public',
        link='http://friend.com',
        content='Friends only body',
        friends_only=True,
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )
    service.public = True
    service.save()

    response = client.post(
        reverse('api', kwargs={'cmd': 'getcontent'}), {'entry': entry.pk}
    )

    assert response.status_code == 200
    assert 'Friends only body' not in response.content.decode()
    assert 'friends-only-entry' in response.content.decode()
    assert 'Friends Login' not in response.content.decode()


@override_settings(MAGICSSO_ENABLED=True)
@pytest.mark.django_db
def test_api_getcontent_shows_magic_sso_login_when_enabled(client, service):
    entry = Entry.objects.create(
        service=service,
        title='Friends',
        guid='fo-public-sso',
        link='http://friend.com',
        content='Friends only body',
        friends_only=True,
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )
    service.public = True
    service.save()

    response = client.post(
        reverse('api', kwargs={'cmd': 'getcontent'}), {'entry': entry.pk}
    )

    assert response.status_code == 200
    assert 'Friends Login' in response.content.decode()
    expected_return_url = quote(f'http://testserver/entry/{entry.pk}', safe='')
    assert (
        f'/friends/login/?returnUrl={expected_return_url}' in response.content.decode()
    )


@override_settings(MAGICSSO_ENABLED=True)
@pytest.mark.django_db
def test_api_getcontent_reveals_friends_only_entry_for_magic_sso_friend(
    client, service
):
    entry = Entry.objects.create(
        service=service,
        title='Friends',
        guid='fo-friend-api',
        link='http://friend.com',
        content='Friends only body',
        friends_only=True,
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )
    service.public = True
    service.save()
    client.cookies[settings.MAGICSSO_COOKIE_NAME] = make_magic_sso_token()

    response = client.post(
        reverse('api', kwargs={'cmd': 'getcontent'}), {'entry': entry.pk}
    )

    assert response.status_code == 200
    assert 'Friends only body' in response.content.decode()


@override_settings(MAGICSSO_ENABLED=True)
@pytest.mark.django_db
def test_api_getcontent_does_not_expose_private_service_entries_to_magic_sso_friend(
    client, service
):
    entry = Entry.objects.create(
        service=service,
        title='Private Service Entry',
        guid='private-friend-api',
        link='http://private.com',
        content='Private body',
        friends_only=True,
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )
    service.public = False
    service.save()
    client.cookies[settings.MAGICSSO_COOKIE_NAME] = make_magic_sso_token()

    response = client.post(
        reverse('api', kwargs={'cmd': 'getcontent'}), {'entry': entry.pk}
    )

    assert response.status_code == 200
    assert response.content == b''


@override_settings(MAGICSSO_ENABLED=True)
@pytest.mark.django_db
def test_api_hide_forbidden_for_magic_sso_friend(client, entry):
    client.cookies[settings.MAGICSSO_COOKIE_NAME] = make_magic_sso_token()

    response = client.post(reverse('api', kwargs={'cmd': 'hide'}), {'entry': entry.pk})

    assert response.status_code == 403


@pytest.mark.django_db
def test_api_putcontent_forbidden_for_anonymous(client, entry):
    url = reverse('api', kwargs={'cmd': 'putcontent'})
    response = client.post(url, {'entry': entry.pk, 'content': 'new'})
    assert response.status_code == 403
