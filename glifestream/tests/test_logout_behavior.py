import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse

from glifestream.testsupport.magic_sso import make_magic_sso_token


@pytest.mark.django_db
def test_logout_get_returns_405(client):
    """
    In Django 5.2, LogoutView only accepts POST.
    Verify that GET returns 405.
    """
    User.objects.create_user(username='testuser', password='password')
    client.login(username='testuser', password='password')

    response = client.get(reverse('logout'))
    assert response.status_code == 405


@pytest.mark.django_db
def test_logout_post_succeeds(client):
    """
    Verify that POST successfully logs out the user.
    """
    User.objects.create_user(username='testuser', password='password')
    client.login(username='testuser', password='password')

    # Check session has user
    assert '_auth_user_id' in client.session

    response = client.post(reverse('logout'))
    assert response.status_code == 302  # Redirect after logout

    # Check session no longer has user
    assert '_auth_user_id' not in client.session


@pytest.mark.django_db
def test_logout_post_clears_magic_sso_cookie(client):
    client.cookies[settings.MAGICSSO_COOKIE_NAME] = make_magic_sso_token()

    response = client.post(reverse('logout'))

    assert response.status_code == 302
    assert settings.MAGICSSO_COOKIE_NAME in response.cookies
    assert response.cookies[settings.MAGICSSO_COOKIE_NAME].value == ''


@pytest.mark.django_db
def test_logout_post_clears_both_session_and_magic_sso_cookie(client):
    User.objects.create_user(username='testuser', password='password')
    client.login(username='testuser', password='password')
    client.cookies[settings.MAGICSSO_COOKIE_NAME] = make_magic_sso_token()

    response = client.post(reverse('logout'))

    assert response.status_code == 302
    assert '_auth_user_id' not in client.session
    assert settings.MAGICSSO_COOKIE_NAME in response.cookies
    assert response.cookies[settings.MAGICSSO_COOKIE_NAME].value == ''
