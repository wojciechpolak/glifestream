import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import translation

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
    UserProfile.objects.create(user=user, language='cs')
    client.login(username='staff', password='password')

    assert _get_index(client, 'en')['Content-Language'] == 'en'


@pytest.mark.django_db
@pytest.mark.parametrize(
    'language', [code for code, _name in settings.LANGUAGES if code != 'en']
)
def test_every_offered_language_translates_the_interface(client, language):
    response = _get_index(client, language)

    assert response['Content-Language'] == language
    with translation.override(language):
        search = translation.gettext('Search this site')
    assert search != 'Search this site'
    content = response.content.decode()
    assert f'<html lang="{language}">' in content
    assert search in content


@pytest.mark.django_db
def test_a_generic_browser_language_finds_its_regional_translation(client):
    response = _get_index(client, 'pt')

    assert response['Content-Language'] == 'pt-br'


@pytest.mark.django_db
def test_a_chinese_browser_region_finds_the_simplified_script(client):
    response = _get_index(client, 'zh-CN')

    assert response['Content-Language'] == 'zh-hans'
