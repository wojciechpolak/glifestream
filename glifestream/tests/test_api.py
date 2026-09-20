import pytest
import datetime
from unittest.mock import patch
from urllib.parse import quote
from django.conf import settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.test import override_settings
from glifestream.stream.models import Entry, Favorite, Service
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


@pytest.fixture
def selfposts_service(db):
    return Service.objects.create(
        name='Selfposts', api='selfposts', cls='notes', url='', public=True
    )


def api_url(cmd):
    return reverse('api', kwargs={'cmd': cmd})


@pytest.mark.django_db
def test_api_refuses_anonymous_access_to_everything_but_getcontent(client, entry):
    for cmd in ('hide', 'unhide', 'gsc', 'share', 'reshare', 'favorite', 'putcontent'):
        response = client.post(api_url(cmd), {'entry': entry.pk})
        assert response.status_code == 403, cmd


@pytest.mark.django_db
def test_api_answers_an_unknown_command_with_an_empty_ok(admin_client):
    response = admin_client.post(api_url('nosuchcmd'))

    assert response.status_code == 200
    assert response.content == b''


@pytest.mark.django_db
@pytest.mark.parametrize(
    'cmd', ['hide', 'unhide', 'reshare', 'favorite', 'unfavorite', 'putcontent']
)
def test_api_commands_needing_an_entry_answer_empty_without_one(admin_client, cmd):
    response = admin_client.post(api_url(cmd))

    assert response.status_code == 200
    assert response.content == b''


@pytest.mark.django_db
def test_api_commands_ignore_an_entry_that_is_gone(admin_client, entry):
    missing = entry.pk + 999
    for cmd in ('reshare', 'favorite', 'unfavorite', 'getcontent', 'putcontent'):
        response = admin_client.post(api_url(cmd), {'entry': missing})
        assert response.status_code == 200, cmd
        assert response.content == b'', cmd


@pytest.mark.django_db
def test_api_gsc_returns_one_service_per_selfposts_class(admin_client):
    first = Service.objects.create(name='Notes A', api='selfposts', cls='notes', url='')
    Service.objects.create(name='Notes B', api='selfposts', cls='notes', url='')
    photos = Service.objects.create(
        name='Photos', api='selfposts', cls='photos', url=''
    )
    Service.objects.create(name='A Feed', api='feed', cls='notes', url='')

    response = admin_client.post(api_url('gsc'))

    assert response.status_code == 200
    assert response.json() == [
        {'id': first.pk, 'cls': 'notes'},
        {'id': photos.pk, 'cls': 'photos'},
    ]


@pytest.mark.django_db
def test_api_share_returns_a_stream_fragment_for_xhr(admin_client, selfposts_service):
    with patch('glifestream.stream.api_view.websub.publish') as publish:
        response = admin_client.post(
            api_url('share'),
            {'content': 'Hello from the tests'},
            headers={'x-requested-with': 'XMLHttpRequest'},
        )

    assert response.status_code == 200
    assert 'Hello from the tests' in response.content.decode()
    publish.assert_called_once()
    assert Entry.objects.filter(service=selfposts_service).count() == 1


@pytest.mark.django_db
def test_api_share_redirects_a_plain_form_post(admin_client, selfposts_service):
    with patch('glifestream.stream.api_view.websub.publish'):
        response = admin_client.post(api_url('share'), {'content': 'Posted by form'})

    assert response.status_code == 302
    assert response['Location'] == settings.BASE_URL + '/'


@pytest.mark.django_db
def test_api_share_of_a_draft_does_not_ping_the_hubs(admin_client, selfposts_service):
    with patch('glifestream.stream.api_view.websub.publish') as publish:
        admin_client.post(
            api_url('share'),
            {'content': 'Not ready yet', 'draft': '1'},
            headers={'x-requested-with': 'XMLHttpRequest'},
        )

    publish.assert_not_called()


@pytest.mark.django_db
def test_api_share_collects_up_to_five_image_urls(admin_client, selfposts_service):
    posted = {'content': 'With images'}
    for i in range(0, 6):
        posted['image%d' % i] = 'http://img.example/%d.jpg' % i

    with (
        patch('glifestream.stream.api_view.websub.publish'),
        patch(
            'glifestream.apis.selfposts.media.save_image',
            side_effect=lambda url, **kw: url,
        ) as save_image,
    ):
        admin_client.post(api_url('share'), posted)

    assert save_image.call_count == 5
    assert 'http://img.example/5.jpg' not in [
        c.args[0] for c in save_image.call_args_list
    ]


@pytest.mark.django_db
def test_api_share_answers_empty_when_the_post_could_not_be_created(admin_client):
    with patch('glifestream.apis.selfposts.SelfpostsService.share', return_value=None):
        response = admin_client.post(api_url('share'), {'content': 'nope'})

    assert response.status_code == 200
    assert response.content == b''


@pytest.mark.django_db
def test_api_reshare_renders_the_new_entry(admin_client, entry, selfposts_service):
    entry.content = 'Something worth resharing'
    entry.save()

    with patch('glifestream.stream.api_view.websub.publish') as publish:
        response = admin_client.post(api_url('reshare'), {'entry': entry.pk})

    assert response.status_code == 200
    assert 'Something worth resharing' in response.content.decode()
    publish.assert_called_once()


@pytest.mark.django_db
def test_api_reshare_answers_empty_when_the_reshare_fails(admin_client, entry):
    with (
        patch('glifestream.apis.selfposts.SelfpostsService.reshare', return_value=None),
        patch('glifestream.stream.api_view.websub.publish') as publish,
    ):
        response = admin_client.post(api_url('reshare'), {'entry': entry.pk})

    assert response.status_code == 200
    assert response.content == b''
    publish.assert_not_called()


@pytest.mark.django_db
def test_api_favorite_twice_keeps_a_single_row(admin_client, entry):
    admin_user = User.objects.get(username='admin')

    admin_client.post(api_url('favorite'), {'entry': entry.pk})
    admin_client.post(api_url('favorite'), {'entry': entry.pk})

    assert Favorite.objects.filter(user=admin_user, entry=entry).count() == 1


@pytest.mark.django_db
def test_api_getcontent_raw_is_only_for_authenticated_callers(
    admin_client, client, service
):
    entry = Entry.objects.create(
        service=service,
        title='Raw',
        guid='raw-1',
        link='http://raw.example/',
        content='tea & biscuits',
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )
    service.public = True
    service.save()

    authed = admin_client.post(api_url('getcontent'), {'entry': entry.pk, 'raw': '1'})
    assert authed.content == b'tea & biscuits'

    # An anonymous caller gets the rendered body instead, ampersands and all.
    anonymous = client.post(api_url('getcontent'), {'entry': entry.pk, 'raw': '1'})
    assert anonymous.content != b'tea & biscuits'
    assert 'tea &amp; biscuits' in anonymous.content.decode()


@pytest.mark.django_db
def test_api_getcontent_hides_a_draft_from_anonymous_callers(client, service):
    entry = Entry.objects.create(
        service=service,
        title='Draft',
        guid='draft-1',
        link='http://draft.example/',
        content='Unfinished',
        draft=True,
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )
    service.public = True
    service.save()

    response = client.post(api_url('getcontent'), {'entry': entry.pk})

    assert response.status_code == 200
    assert response.content == b''


@pytest.mark.django_db
def test_api_putcontent_updates_and_renders(admin_client, entry):
    response = admin_client.post(
        api_url('putcontent'), {'entry': entry.pk, 'content': 'Edited body'}
    )

    assert response.status_code == 200
    assert 'Edited body' in response.content.decode()
    entry.refresh_from_db()
    assert entry.content == 'Edited body'


@pytest.mark.django_db
def test_api_putcontent_with_no_content_leaves_the_entry_alone(admin_client, entry):
    entry.content = 'Unchanged'
    entry.save()

    response = admin_client.post(api_url('putcontent'), {'entry': entry.pk})

    assert response.status_code == 200
    entry.refresh_from_db()
    assert entry.content == 'Unchanged'
