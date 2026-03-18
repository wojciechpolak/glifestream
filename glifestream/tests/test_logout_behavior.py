import pytest
from django.contrib.auth.models import User
from django.urls import reverse


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
