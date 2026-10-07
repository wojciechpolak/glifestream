import pytest
import datetime
from PIL import Image
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote
from django.conf import settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.test import override_settings
from glifestream.stream.models import Entry, Favorite, Service, WebSubPublishRequest
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


@pytest.fixture
def hubs():
    """The WebSub hubs and the worker's wake socket, neither of them real."""
    with (
        patch('glifestream.stream.websub.publish') as publish,
        patch('glifestream.fetching.send_worker_wake_signal') as wake,
    ):
        yield SimpleNamespace(publish=publish, wake=wake)


def assert_publish_requested(hubs, count=1):
    # The view leaves the hubs to the worker, and wakes it to tell them.
    assert WebSubPublishRequest.objects.count() == count
    assert hubs.wake.call_count == count
    hubs.publish.assert_not_called()


@pytest.mark.django_db
def test_api_share_returns_a_stream_fragment_for_xhr(
    admin_client, selfposts_service, hubs
):
    response = admin_client.post(
        api_url('share'),
        {'content': 'Hello from the tests'},
        headers={'x-requested-with': 'XMLHttpRequest'},
    )

    assert response.status_code == 200
    assert 'Hello from the tests' in response.content.decode()
    assert_publish_requested(hubs)
    assert Entry.objects.filter(service=selfposts_service).count() == 1


@pytest.mark.django_db
def test_api_share_redirects_a_plain_form_post(admin_client, selfposts_service, hubs):
    response = admin_client.post(api_url('share'), {'content': 'Posted by form'})

    assert response.status_code == 302
    assert response['Location'] == settings.BASE_URL + '/'


@pytest.mark.django_db
def test_api_share_of_a_draft_does_not_ping_the_hubs(
    admin_client, selfposts_service, hubs
):
    admin_client.post(
        api_url('share'),
        {'content': 'Not ready yet', 'draft': '1'},
        headers={'x-requested-with': 'XMLHttpRequest'},
    )

    assert_publish_requested(hubs, count=0)


@pytest.mark.django_db
def test_api_share_collects_up_to_five_image_urls(
    admin_client, selfposts_service, hubs
):
    posted = {'content': 'With images'}
    for i in range(0, 6):
        posted['image%d' % i] = 'http://img.example/%d.jpg' % i

    with patch(
        'glifestream.apis.selfposts.media.save_image',
        side_effect=lambda url, **kw: url,
    ) as save_image:
        admin_client.post(api_url('share'), posted)

    assert save_image.call_count == 5
    assert 'http://img.example/5.jpg' not in [
        c.args[0] for c in save_image.call_args_list
    ]


@pytest.mark.django_db
def test_api_share_passes_the_music_track_on(admin_client, selfposts_service, hubs):
    with patch(
        'glifestream.apis.selfposts.SelfpostsService.share', return_value=None
    ) as share:
        admin_client.post(
            api_url('share'),
            {'content': '', 'music_artist': 'Artist', 'music_title': 'Title'},
        )

    assert share.call_args.args[0]['music'] == {
        'artist': 'Artist',
        'title': 'Title',
        'youtube': '',
        'cover': '',
    }


@pytest.mark.django_db
def test_api_share_answers_empty_when_the_post_could_not_be_created(admin_client):
    with patch('glifestream.apis.selfposts.SelfpostsService.share', return_value=None):
        response = admin_client.post(api_url('share'), {'content': 'nope'})

    assert response.status_code == 200
    assert response.content == b''


@pytest.mark.django_db
def test_api_reshare_renders_the_new_entry(
    admin_client, entry, selfposts_service, hubs
):
    entry.content = 'Something worth resharing'
    entry.save()

    response = admin_client.post(api_url('reshare'), {'entry': entry.pk})

    assert response.status_code == 200
    assert 'Something worth resharing' in response.content.decode()
    assert_publish_requested(hubs)


@pytest.mark.django_db
def test_api_reshare_answers_empty_when_the_reshare_fails(admin_client, entry, hubs):
    with patch(
        'glifestream.apis.selfposts.SelfpostsService.reshare', return_value=None
    ):
        response = admin_client.post(api_url('reshare'), {'entry': entry.pk})

    assert response.status_code == 200
    assert response.content == b''
    assert_publish_requested(hubs, count=0)


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


THUMB = '[GLS-THUMBS]/ad97b17ffccd1af56d7f1596ff2b47f4e6a487bf.webp'
EDITOR_PLAYER = (
    '<div data-id="youtube-abc" class="play-video">'
    '<a href="https://www.youtube.com/watch?v=abc" rel="nofollow">'
    '<img src="https://i.ytimg.com/vi/abc/mqdefault.jpg" width="320" height="180" '
    'alt="YouTube Video"></a><div class="playbutton"></div></div>'
)


@pytest.mark.django_db
def test_api_getcontent_raw_gives_the_editor_addresses_it_can_show(admin_client, entry):
    entry.content = '<img src="%s"><a href="[GLS-UPLOAD]/a.pdf">a</a>' % THUMB
    entry.save()

    raw = admin_client.post(api_url('getcontent'), {'entry': entry.pk, 'raw': '1'})

    assert raw.content.decode() == (
        '<img src="%sthumbs/a/%s"><a href="%supload/a.pdf">a</a>'
        % (settings.MEDIA_URL, THUMB.split('/')[1], settings.MEDIA_URL)
    )

    admin_client.post(
        api_url('putcontent'), {'entry': entry.pk, 'content': raw.content.decode()}
    )
    entry.refresh_from_db()
    assert entry.content == '<img src="%s"><a href="[GLS-UPLOAD]/a.pdf">a</a>' % THUMB
    # Only a post gets its players made again.
    assert entry.mblob is None


@pytest.mark.django_db
def test_api_putcontent_gives_a_post_its_players(admin_client, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.APP_THUMBNAIL_FORMAT = 'WEBP'
    # The thumbnail a download leaves, which is then current.
    name = THUMB.split('/')[1]
    (tmp_path / 'thumbs' / name[0]).mkdir(parents=True)
    (tmp_path / 'thumbs' / name[0] / name).write_bytes(b'thumb')
    post = Service.objects.create(name='Videos', api='selfposts', public=True)
    entry = Entry.objects.create(
        service=post,
        title='Post',
        guid='post-1',
        link='http://test.com',
        mblob='{"content": [[{"url": "[GLS-UPLOAD]/p.jpg", "medium": "image"}]]}',
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )
    edited = '<div>Two:</div>%s<div>https://youtu.be/def</div>' % EDITOR_PLAYER

    with patch(
        'glifestream.filters.players.media.save_image', return_value=THUMB
    ) as save:
        admin_client.post(api_url('putcontent'), {'entry': entry.pk, 'content': edited})

    entry.refresh_from_db()
    assert save.call_count == 2
    assert entry.content.count('src="%s" width="320" height="180"' % THUMB) == 2
    assert 'data-id="youtube-def"' in entry.content
    assert 'i.ytimg.com' not in entry.content
    assert entry.mblob is not None
    assert 'youtube.com/embed/abc' in entry.mblob
    assert 'youtube.com/embed/def' in entry.mblob
    assert '[GLS-UPLOAD]/p.jpg' in entry.mblob


@pytest.fixture
def posts(db):
    return Service.objects.create(name='Notes', api='selfposts', public=True)


@pytest.mark.django_db
def test_api_preview_shows_a_post_as_the_stream_will_and_saves_nothing(
    admin_client, client, posts
):
    count = Entry.objects.count()

    response = admin_client.post(
        api_url('preview'),
        {'sid': posts.pk, 'content': 'Hello *world*', 'friends_only': '1'},
    )

    body = response.content.decode()
    assert response.status_code == 200
    assert '<article' in body and 'class="hentry e-selfposts' in body
    assert 'world' in body
    assert 'id="entry-' not in body and 'shareit' not in body
    # The owner sees the content friends will, and its lock.
    assert 'friends-only-entry' not in body
    assert 'friends-only-lock' in body
    assert Entry.objects.count() == count
    assert client.post(api_url('preview'), {'content': 'x'}).status_code == 403


@pytest.mark.django_db
def test_api_preview_shows_the_music_card(admin_client, posts):
    response = admin_client.post(
        api_url('preview'),
        {'sid': posts.pk, 'music_artist': 'Band', 'music_title': 'Song'},
    )

    body = response.content.decode()
    assert '<div class="music-card">' in body
    assert 'Song – Band' in body


@pytest.mark.django_db
def test_api_preview_of_an_edit_leaves_the_entry_alone(
    admin_client, posts, settings, tmp_path
):
    settings.MEDIA_ROOT = str(tmp_path)
    entry = Entry.objects.create(
        service=posts,
        title='Post',
        guid='post-preview',
        link='http://test.com',
        content='<div>Old</div>',
        date_published=datetime.datetime(2023, 11, 1, 12, 0, tzinfo=UTC),
    )

    with patch('glifestream.filters.players.media.save_image', return_value=THUMB):
        response = admin_client.post(
            api_url('preview'),
            {'entry': entry.pk, 'content': '<div>New</div>%s' % EDITOR_PLAYER},
        )

    body = response.content.decode()
    assert 'New' in body and 'Old' not in body
    assert 'data-id="youtube-abc"' in body
    assert '/thumbs/a/%s' % THUMB.split('/')[1] in body
    entry.refresh_from_db()
    assert entry.content == '<div>Old</div>'
    missing = admin_client.post(api_url('preview'), {'entry': 999999, 'content': 'x'})
    assert missing.content == b''


MUSIC_CARD = (
    '<div class="music-card"><span class="music-cover"><img src="%s" width="160" '
    'height="160" alt="Brave Men – Shoelace" /></span><p class="music-track">'
    '<span class="music-title">Brave Men</span> <span class="music-artist">'
    'Shoelace</span></p><p class="music-links"></p></div>' % THUMB
)


@pytest.fixture
def music_post(db, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    name = THUMB.split('/')[1]
    (tmp_path / 'thumbs' / name[0]).mkdir(parents=True)
    Image.new('RGB', (160, 160)).save(tmp_path / 'thumbs' / name[0] / name, 'WEBP')
    music = Service.objects.create(
        name='Music', api='selfposts', cls='music', public=True
    )
    Service.objects.create(name='Blog', api='selfposts', cls='blog', public=True)
    return Entry.objects.create(
        service=music,
        title='Brave Men',
        guid='music-post',
        link='http://test.com',
        content=MUSIC_CARD + '\n<p>Loved it.</p>',
        date_published=datetime.datetime(2010, 1, 1, 12, 0, tzinfo=UTC),
    )


@pytest.mark.django_db
def test_api_editcontent_gives_the_composer_the_post_and_its_class(
    admin_client, client, music_post, entry
):
    data = admin_client.post(api_url('editcontent'), {'entry': music_post.pk}).json()

    shown = MUSIC_CARD.replace(
        THUMB, '%sthumbs/a/%s' % (settings.MEDIA_URL, THUMB.split('/')[1])
    )
    assert data == {
        'content': shown + '\n<p>Loved it.</p>',
        'cls': 'music',
        'post': True,
        'draft': False,
        'friends_only': False,
    }
    # An imported entry has the class of its service, which stays.
    other = admin_client.post(api_url('editcontent'), {'entry': entry.pk}).json()
    assert (other['cls'], other['post']) == ('feed', False)
    assert client.post(api_url('editcontent'), {'entry': entry.pk}).status_code == 403


def edited_card(title: str, cover: str) -> str:
    """A card as the editor writes it: what it shows, without its links."""
    return (
        '<div class="music-card"><span class="music-cover"><img src="%s" '
        'width="160" height="160" alt=""></span><p class="music-track">'
        '<span class="music-title">%s</span> <span class="music-artist">Shoelace'
        '</span></p><p class="music-links"></p></div>' % (cover, title)
    )


@pytest.mark.django_db
def test_api_putcontent_makes_the_card_again_and_moves_the_post_to_a_class(
    admin_client, music_post
):
    blog = Service.objects.get(cls='blog')
    published = music_post.date_published
    shown = '%sthumbs/a/%s' % (settings.MEDIA_URL, THUMB.split('/')[1])

    response = admin_client.post(
        api_url('putcontent'),
        {
            'entry': music_post.pk,
            'content': edited_card('Brave Men (live)', shown) + '<p>Loved it.</p>',
            'sid': blog.pk,
            'article': '1',
        },
    )

    music_post.refresh_from_db()
    assert music_post.service == blog
    assert music_post.date_published == published
    assert music_post.content.startswith('<div class="music-card">')
    assert '<span class="music-title">Brave Men (live)</span>' in music_post.content
    # Made again, with its links and the cover it had.
    assert 'open.spotify.com/search/Shoelace%20Brave%20Men%20%28live%29' in (
        music_post.content
    )
    assert 'src="%s"' % THUMB in music_post.content
    body = response.content.decode()
    assert body.lstrip().startswith('<article id="entry-%d"' % music_post.pk)
    assert 'e-blog' in body

    # A class of its own leaves the post where it is.
    admin_client.post(
        api_url('putcontent'),
        {'entry': music_post.pk, 'content': '<p>Just text.</p>', 'sid': blog.pk},
    )
    music_post.refresh_from_db()
    assert music_post.content == '<p>Just text.</p>'
    assert music_post.service == blog


@pytest.mark.django_db
def test_api_preview_of_an_edit_shows_its_new_class_and_card(admin_client, music_post):
    blog = Service.objects.get(cls='blog')

    body = admin_client.post(
        api_url('preview'),
        {
            'entry': music_post.pk,
            'content': edited_card('Other Song', THUMB) + '<p>Loved it.</p>',
            'sid': blog.pk,
        },
    ).content.decode()

    assert 'e-blog' in body
    assert '<span class="music-title">Other Song</span>' in body
    assert 'Bandcamp' in body
    music_post.refresh_from_db()
    assert music_post.service.cls == 'music'


@pytest.mark.django_db
def test_api_putcontent_saves_the_checkboxes_of_the_composer(admin_client, music_post):
    response = admin_client.post(
        api_url('putcontent'),
        {
            'entry': music_post.pk,
            'content': '<p>For friends.</p>',
            'friends_only': '1',
            'draft': '0',
            'article': '1',
        },
    )

    music_post.refresh_from_db()
    assert music_post.friends_only and not music_post.draft
    # The owner sees the content, and the lock the stream shows.
    body = response.content.decode()
    assert 'For friends.' in body and 'friends-only-lock' in body
    assert admin_client.post(api_url('editcontent'), {'entry': music_post.pk}).json()[
        'friends_only'
    ]

    # The raw editor sends no checkboxes, and changes neither.
    admin_client.post(
        api_url('putcontent'), {'entry': music_post.pk, 'content': '<p>Raw.</p>'}
    )
    music_post.refresh_from_db()
    assert music_post.friends_only
