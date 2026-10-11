import re

import pytest
from io import StringIO
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
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
def test_middleware_blocks_admin_until_password_is_changed(client):
    user = User.objects.create_superuser(username='inituser', password='initpass')
    UserProfile.objects.create(user=user, must_change_password=True)
    client.login(username='inituser', password='initpass')

    response = client.get('/admin/')
    assert response.status_code == 302
    assert response['Location'] == reverse('change-password')


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
@pytest.mark.parametrize(
    'new_password, message',
    [
        ('admin', b'must differ from the current one'),
        ('short', b'too short'),
        ('password123', b'too common'),
        ('83917264530', b'entirely numeric'),
    ],
)
def test_change_password_rejects_a_weak_or_unchanged_password(
    client, new_password, message
):
    user = User.objects.create_user(username='admin', password='admin', is_staff=True)
    UserProfile.objects.create(user=user, must_change_password=True)
    client.login(username='admin', password='admin')

    response = client.post(
        reverse('change-password'),
        {'new_password1': new_password, 'new_password2': new_password},
    )

    assert response.status_code == 200
    assert message in response.content
    user.refresh_from_db()
    assert user.check_password('admin')
    assert UserProfile.objects.get(user=user).must_change_password is True


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
    call_command(
        'create_initial_user',
        '--password=correct horse battery staple',
        stdout=out,
    )
    output = out.getvalue()
    assert 'created' in output.lower()

    user = User.objects.get(username='admin')
    assert user.is_superuser
    assert user.is_staff
    assert user.check_password('correct horse battery staple')

    profile = UserProfile.objects.get(user=user)
    assert profile.must_change_password is True


@pytest.mark.django_db
def test_create_initial_user_idempotent(monkeypatch):
    call_command('create_initial_user', '--password=correct horse battery staple')
    monkeypatch.setenv('INITIAL_ADMIN_PASSWORD', 'a password left set')

    out = StringIO()
    call_command('create_initial_user', stdout=out)
    output = out.getvalue()
    assert 'already exists' in output.lower()

    assert User.objects.filter(username='admin').count() == 1
    user = User.objects.get(username='admin')
    assert user.check_password('correct horse battery staple')


@pytest.mark.django_db
def test_create_initial_user_leaves_a_changed_account_alone(monkeypatch):
    monkeypatch.delenv('INITIAL_ADMIN_PASSWORD', raising=False)
    # Made with createsuperuser under an older release, so without a profile,
    # and since demoted on purpose.
    user = User.objects.create_user(username='admin', password='owner secret')

    call_command('create_initial_user', stdout=StringIO())

    user.refresh_from_db()
    assert user.check_password('owner secret')
    assert not user.is_superuser
    assert not UserProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_create_initial_user_replaces_the_legacy_default_password(monkeypatch):
    monkeypatch.delenv('INITIAL_ADMIN_PASSWORD', raising=False)
    user = User.objects.create_superuser(username='admin', password='admin')

    out = StringIO()
    call_command('create_initial_user', stdout=out)

    generated = _generated_password(out.getvalue())
    user.refresh_from_db()
    assert not user.check_password('admin')
    assert user.check_password(generated)
    assert UserProfile.objects.get(user=user).must_change_password is True


@pytest.mark.django_db
def test_create_initial_user_replaces_the_legacy_default_from_environment(
    monkeypatch,
):
    password = 'protected replacement for legacy administrator'
    monkeypatch.setenv('INITIAL_ADMIN_PASSWORD', password)
    user = User.objects.create_superuser(username='admin', password='admin')
    UserProfile.objects.create(user=user, must_change_password=False)

    call_command('create_initial_user', stdout=StringIO())

    user.refresh_from_db()
    assert user.check_password(password)
    assert UserProfile.objects.get(user=user).must_change_password is True


@pytest.mark.django_db
def test_create_initial_user_force():
    call_command('create_initial_user', '--password=correct horse battery staple')
    user = User.objects.get(username='admin')
    user.set_password('changed')
    user.save()
    profile = UserProfile.objects.get(user=user)
    profile.must_change_password = False
    profile.save()

    out = StringIO()
    call_command(
        'create_initial_user',
        '--force',
        '--password=another correct horse battery staple',
        stdout=out,
    )
    output = out.getvalue()
    assert 'reset' in output.lower()

    user.refresh_from_db()
    assert user.check_password('another correct horse battery staple')
    profile.refresh_from_db()
    assert profile.must_change_password is True


@pytest.mark.django_db
def test_create_initial_user_custom_credentials():
    out = StringIO()
    call_command(
        'create_initial_user',
        '--username=testadmin',
        '--password=custom test administrator secret',
        stdout=out,
    )

    user = User.objects.get(username='testadmin')
    assert user.check_password('custom test administrator secret')
    assert user.is_superuser

    profile = UserProfile.objects.get(user=user)
    assert profile.must_change_password is True


@pytest.mark.django_db
def test_create_initial_user_generates_and_prints_a_password(monkeypatch):
    monkeypatch.delenv('INITIAL_ADMIN_PASSWORD', raising=False)

    out = StringIO()
    call_command('create_initial_user', stdout=out)

    user = User.objects.get(username='admin')
    assert user.check_password(_generated_password(out.getvalue()))
    assert user.is_superuser
    assert UserProfile.objects.get(user=user).must_change_password is True


@pytest.mark.django_db
def test_create_initial_user_force_without_password_generates_one(monkeypatch):
    monkeypatch.delenv('INITIAL_ADMIN_PASSWORD', raising=False)
    call_command('create_initial_user', '--password=correct horse battery staple')

    out = StringIO()
    call_command('create_initial_user', '--force', stdout=out)

    user = User.objects.get(username='admin')
    assert user.check_password(_generated_password(out.getvalue()))


def _generated_password(output: str) -> str:
    match = re.search(r'Generated password for "[^"]+": (\S+)', output)
    assert match, output
    return match.group(1)


@pytest.mark.django_db
@pytest.mark.parametrize(
    'password',
    ['admin', 'change-me-to-a-strong-initial-admin-password'],
)
def test_create_initial_user_rejects_known_bootstrap_passwords(password):
    with pytest.raises(CommandError, match='known placeholder'):
        call_command('create_initial_user', password=password)

    assert not User.objects.filter(username='admin').exists()


@pytest.mark.django_db
def test_create_initial_user_reads_password_from_environment(monkeypatch):
    password = 'environment supplied bootstrap secret'
    monkeypatch.setenv('INITIAL_ADMIN_PASSWORD', password)

    call_command('create_initial_user')

    assert User.objects.get(username='admin').check_password(password)
