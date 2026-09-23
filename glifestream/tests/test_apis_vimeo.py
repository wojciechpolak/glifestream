import datetime
import pytest
from unittest.mock import patch

from glifestream.apis.vimeo import VimeoService, filter_title
from glifestream.stream.models import Entry
from glifestream.utils import httpclient

UTC = datetime.timezone.utc


@pytest.mark.django_db
def test_vimeo_fetch_error_propagates(service):
    service.api = 'vimeo'
    service.url = 'channel/staffpicks'
    service.save()

    api = VimeoService(service)

    with (
        patch(
            'glifestream.apis.vimeo.httpclient.get',
            side_effect=httpclient.build_fetch_error(
                category='remote_5xx',
                detail='HTTP 503 Service Unavailable from https://vimeo.com/api/v2/channel/staffpicks/videos.json',
                retryable=True,
                status_code=503,
                url='https://vimeo.com/api/v2/channel/staffpicks/videos.json',
            ),
        ),
        pytest.raises(httpclient.FetchError) as excinfo,
    ):
        api.run()

    assert excinfo.value.category == 'remote_5xx'


def clip(clip_id='123', date_key='upload_date', date='2026-03-22 17:00:00', **extra):
    ent = {
        'id': clip_id,
        'title': 'A Clip',
        'url': 'https://vimeo.com/%s' % clip_id,
        'user_name': 'Someone',
        'thumbnail_large': 'https://i.vimeo.example/%s.jpg' % clip_id,
        date_key: date,
    }
    ent.update(extra)
    return ent


@pytest.fixture
def vimeo(service):
    service.api = 'vimeo'
    service.url = 'someone'
    service.save()
    return VimeoService(service)


@pytest.mark.django_db
def test_get_urls_for_a_user_covers_likes_and_uploads(vimeo):
    assert vimeo.get_urls() == [
        'https://vimeo.com/someone/likes/rss',
        'https://vimeo.com/someone/videos/rss',
    ]


@pytest.mark.django_db
def test_get_urls_for_a_channel_normalizes_the_path(vimeo):
    vimeo.service.url = 'channel/staffpicks'

    assert vimeo.get_urls() == ['https://vimeo.com/channels/staffpicks/videos/rss']


@pytest.mark.django_db
def test_process_videos_creates_an_entry(vimeo):
    vimeo.json = [clip()]

    with (
        patch(
            'glifestream.apis.vimeo.media.save_image', side_effect=lambda url, **kw: url
        ),
        patch('glifestream.apis.vimeo.media.extract_and_register') as register,
    ):
        vimeo.process_videos()

    entry = Entry.objects.get()
    assert entry.guid == 'tag:vimeo,2026-03-22:clip123'
    assert entry.title == 'A Clip'
    assert entry.author_name == 'Someone'
    assert entry.idata == ''
    assert entry.date_published == datetime.datetime(2026, 3, 22, 17, 0, tzinfo=UTC)
    assert 'player.vimeo.com/video/123' in entry.mblob
    register.assert_called_once()


@pytest.mark.django_db
def test_process_likes_tags_the_entry_and_skips_media_registration(vimeo):
    vimeo.json = [clip(date_key='liked_on')]

    with (
        patch(
            'glifestream.apis.vimeo.media.save_image', side_effect=lambda url, **kw: url
        ),
        patch('glifestream.apis.vimeo.media.extract_and_register') as register,
    ):
        vimeo.process_likes()

    assert Entry.objects.get().idata == 'liked'
    register.assert_not_called()


@pytest.mark.django_db
def test_process_keeps_a_thumbnail_remote_for_a_private_service(vimeo):
    vimeo.service.public = False
    vimeo.service.save()
    vimeo.json = [clip()]

    with patch('glifestream.apis.vimeo.media.save_image') as save_image:
        vimeo.process_videos()

    save_image.assert_not_called()
    assert 'i.vimeo.example/123.jpg' in Entry.objects.get().content


@pytest.mark.django_db
def test_process_passes_an_unfamiliar_timestamp_straight_through(vimeo):
    """Vimeo's own format is parsed; anything else is left for Django."""
    vimeo.json = [clip(date='2026-03-22T17:00:00+00:00')]

    with patch(
        'glifestream.apis.vimeo.media.save_image', side_effect=lambda url, **kw: url
    ):
        vimeo.process_videos()

    assert Entry.objects.get().date_published == datetime.datetime(
        2026, 3, 22, 17, 0, tzinfo=UTC
    )


@pytest.mark.django_db
def test_process_drops_an_entry_with_an_unusable_timestamp(vimeo):
    vimeo.json = [clip(date='not a date at all')]

    with patch(
        'glifestream.apis.vimeo.media.save_image', side_effect=lambda url, **kw: url
    ):
        vimeo.process_videos()

    assert not Entry.objects.exists()


@pytest.mark.django_db
def test_process_skips_an_entry_that_has_not_changed(vimeo):
    vimeo.json = [clip()]
    with patch(
        'glifestream.apis.vimeo.media.save_image', side_effect=lambda url, **kw: url
    ):
        vimeo.process_videos()
        Entry.objects.update(title='Edited by hand')
        vimeo.process_videos()

    assert Entry.objects.get().title == 'Edited by hand'


@pytest.mark.django_db
def test_force_overwrite_rewrites_an_unchanged_entry(vimeo):
    vimeo.json = [clip()]
    with patch(
        'glifestream.apis.vimeo.media.save_image', side_effect=lambda url, **kw: url
    ):
        vimeo.process_videos()
        Entry.objects.update(title='Edited by hand')
        vimeo.force_overwrite = True
        vimeo.process_videos()

    assert Entry.objects.get().title == 'A Clip'


@pytest.mark.django_db
def test_process_never_touches_a_protected_entry(vimeo):
    vimeo.json = [clip()]
    with patch(
        'glifestream.apis.vimeo.media.save_image', side_effect=lambda url, **kw: url
    ):
        vimeo.process_videos()
        Entry.objects.update(protected=True, title='Hands off')
        vimeo.force_overwrite = True
        vimeo.process_videos()

    assert Entry.objects.get().title == 'Hands off'


@pytest.mark.django_db
def test_process_is_chatty_when_verbose(vimeo, capsys):
    vimeo.verbose = 1
    vimeo.json = [clip()]

    with patch(
        'glifestream.apis.vimeo.media.save_image', side_effect=lambda url, **kw: url
    ):
        vimeo.process_videos()

    assert 'tag:vimeo,2026-03-22:clip123' in capsys.readouterr().out


@pytest.mark.django_db
def test_run_fetches_likes_then_videos_for_a_user(vimeo):
    with patch.object(VimeoService, 'fetch') as fetch:
        vimeo.run()

    assert [call.args[0] for call in fetch.call_args_list] == [
        '/api/v2/someone/likes.json',
        '/api/v2/someone/videos.json',
    ]
    assert vimeo.service.link == 'https://vimeo.com/someone'


@pytest.mark.django_db
def test_run_fetches_only_videos_for_a_channel(vimeo):
    vimeo.service.url = 'channel/staffpicks'

    with patch.object(VimeoService, 'fetch') as fetch:
        vimeo.run()

    assert [call.args[0] for call in fetch.call_args_list] == [
        '/api/v2/channel/staffpicks/videos.json'
    ]


def test_filter_title_distinguishes_a_like_from_an_upload():
    assert 'Liked' in filter_title(Entry(idata='liked', title='A Clip'))
    assert 'Published' in filter_title(Entry(idata='', title='A Clip'))
