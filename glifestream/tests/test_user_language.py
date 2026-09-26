import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from glifestream.gauth.models import UserProfile


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='staff', password='password', is_staff=True
    )


def _get_index(client, accept_language):
    return client.get(reverse('index'), HTTP_ACCEPT_LANGUAGE=accept_language)


@pytest.mark.django_db
def test_the_language_picked_in_settings_wins_over_the_browser(client, user):
    UserProfile.objects.create(user=user, language='pl')
    client.login(username='staff', password='password')

    response = _get_index(client, 'en')

    assert response['Content-Language'] == 'pl'
    content = response.content.decode()
    assert '<html lang="pl">' in content
    assert 'Wyloguj' in content


@pytest.mark.django_db
def test_without_a_pick_the_browser_decides(client, user):
    UserProfile.objects.create(user=user, language='')
    client.login(username='staff', password='password')

    assert _get_index(client, 'pl')['Content-Language'] == 'pl'
    assert _get_index(client, 'en')['Content-Language'] == 'en'


@pytest.mark.django_db
def test_a_user_without_a_profile_follows_the_browser(client, user):
    client.login(username='staff', password='password')

    assert _get_index(client, 'pl')['Content-Language'] == 'pl'


@pytest.mark.django_db
def test_an_anonymous_visitor_follows_the_browser(client):
    response = _get_index(client, 'pl')

    assert response['Content-Language'] == 'pl'
    assert '<html lang="pl">' in response.content.decode()


@pytest.mark.django_db
def test_a_stored_language_without_translations_is_ignored(client, user):
    UserProfile.objects.create(user=user, language='de')
    client.login(username='staff', password='password')

    assert _get_index(client, 'en')['Content-Language'] == 'en'
