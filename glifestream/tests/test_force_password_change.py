import pytest
from io import StringIO
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import reverse

from glifestream.gauth.models import UserProfile


# --- Middleware Tests ---


@pytest.mark.django_db
def test_middleware_redirects_must_change_password_user(client):
    user = User.objects.create_user(
        username='inituser', password='initpass', is_staff=True
    )
    UserProfile.objects.create(user=user, must_change_password=True)
    client.login(username='inituser', password='initpass')

    response = client.get(reverse('index'))
    assert response.status_code == 302
    assert reverse('change-password') in response['Location']


@pytest.mark.django_db
def test_middleware_allows_change_password_page(client):
    user = User.objects.create_user(
        username='inituser', password='initpass', is_staff=True
    )
    UserProfile.objects.create(user=user, must_change_password=True)
    client.login(username='inituser', password='initpass')

    response = client.get(reverse('change-password'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_middleware_allows_logout(client):
    user = User.objects.create_user(
        username='inituser', password='initpass', is_staff=True
    )
    UserProfile.objects.create(user=user, must_change_password=True)
    client.login(username='inituser', password='initpass')

    response = client.post(reverse('logout'))
    assert response.status_code == 302  # logout redirects


@pytest.mark.django_db
def test_middleware_no_redirect_for_normal_user(client):
    user = User.objects.create_user(
        username='normaluser', password='pass', is_staff=True
    )
    UserProfile.objects.create(user=user, must_change_password=False)
    client.login(username='normaluser', password='pass')

    response = client.get(reverse('index'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_middleware_no_redirect_without_profile(client):
    User.objects.create_user(username='noprofile', password='pass', is_staff=True)
    client.login(username='noprofile', password='pass')

    response = client.get(reverse('index'))
    assert response.status_code == 200


# --- Change Password View Tests ---


@pytest.mark.django_db
def test_change_password_get(client):
    user = User.objects.create_user(
        username='cpuser', password='oldpass', is_staff=True
    )
    UserProfile.objects.create(user=user, must_change_password=True)
    client.login(username='cpuser', password='oldpass')

    response = client.get(reverse('change-password'))
    assert response.status_code == 200
    assert b'Change Your Password' in response.content


@pytest.mark.django_db
def test_change_password_success(client):
    user = User.objects.create_user(
        username='cpuser', password='oldpass', is_staff=True
    )
    UserProfile.objects.create(user=user, must_change_password=True)
    client.login(username='cpuser', password='oldpass')

    response = client.post(
        reverse('change-password'),
        {'new_password1': 'newStrongPass123', 'new_password2': 'newStrongPass123'},
    )
    assert response.status_code == 302
    assert response['Location'] == reverse('index')

    # Verify password was changed.
    user.refresh_from_db()
    assert user.check_password('newStrongPass123')

    # Verify flag is cleared.
    profile = UserProfile.objects.get(user=user)
    assert profile.must_change_password is False


@pytest.mark.django_db
def test_change_password_mismatch(client):
    user = User.objects.create_user(
        username='cpuser', password='oldpass', is_staff=True
    )
    UserProfile.objects.create(user=user, must_change_password=True)
    client.login(username='cpuser', password='oldpass')

    response = client.post(
        reverse('change-password'),
        {'new_password1': 'pass1', 'new_password2': 'pass2'},
    )
    assert response.status_code == 200
    assert b'Passwords do not match' in response.content

    # Password should NOT have changed.
    user.refresh_from_db()
    assert user.check_password('oldpass')


@pytest.mark.django_db
def test_change_password_empty_fields(client):
    user = User.objects.create_user(
        username='cpuser', password='oldpass', is_staff=True
    )
    UserProfile.objects.create(user=user, must_change_password=True)
    client.login(username='cpuser', password='oldpass')

    response = client.post(
        reverse('change-password'),
        {'new_password1': '', 'new_password2': ''},
    )
    assert response.status_code == 200
    assert b'Please fill in both password fields' in response.content


@pytest.mark.django_db
def test_change_password_requires_login(client):
    response = client.get(reverse('change-password'))
    assert response.status_code == 302
    assert '/login' in response['Location']


@pytest.mark.django_db
def test_change_password_forbidden_without_flag(client):
    """Users who don't need a password change get 403."""
    user = User.objects.create_user(username='regular', password='pass', is_staff=True)
    UserProfile.objects.create(user=user, must_change_password=False)
    client.login(username='regular', password='pass')

    response = client.get(reverse('change-password'))
    assert response.status_code == 403

    response = client.post(
        reverse('change-password'),
        {'new_password1': 'hack', 'new_password2': 'hack'},
    )
    assert response.status_code == 403
    # Password must not have changed.
    user.refresh_from_db()
    assert user.check_password('pass')


@pytest.mark.django_db
def test_change_password_forbidden_without_profile(client):
    """Users without a UserProfile at all also get 403."""
    User.objects.create_user(username='noprofile', password='pass', is_staff=True)
    client.login(username='noprofile', password='pass')

    response = client.get(reverse('change-password'))
    assert response.status_code == 403


# --- Management Command Tests ---


@pytest.mark.django_db
def test_create_initial_user_command():
    out = StringIO()
    call_command('create_initial_user', stdout=out)
    output = out.getvalue()
    assert 'created' in output.lower()

    user = User.objects.get(username='admin')
    assert user.is_superuser
    assert user.is_staff
    assert user.check_password('admin')

    profile = UserProfile.objects.get(user=user)
    assert profile.must_change_password is True


@pytest.mark.django_db
def test_create_initial_user_idempotent():
    call_command('create_initial_user')

    out = StringIO()
    call_command('create_initial_user', stdout=out)
    output = out.getvalue()
    assert 'already exists' in output.lower()

    assert User.objects.filter(username='admin').count() == 1


@pytest.mark.django_db
def test_create_initial_user_force():
    call_command('create_initial_user')
    user = User.objects.get(username='admin')
    user.set_password('changed')
    user.save()
    profile = UserProfile.objects.get(user=user)
    profile.must_change_password = False
    profile.save()

    out = StringIO()
    call_command('create_initial_user', '--force', stdout=out)
    output = out.getvalue()
    assert 'reset' in output.lower()

    user.refresh_from_db()
    assert user.check_password('admin')
    profile.refresh_from_db()
    assert profile.must_change_password is True


@pytest.mark.django_db
def test_create_initial_user_custom_credentials():
    out = StringIO()
    call_command(
        'create_initial_user', '--username=testadmin', '--password=testpass', stdout=out
    )

    user = User.objects.get(username='testadmin')
    assert user.check_password('testpass')
    assert user.is_superuser

    profile = UserProfile.objects.get(user=user)
    assert profile.must_change_password is True
