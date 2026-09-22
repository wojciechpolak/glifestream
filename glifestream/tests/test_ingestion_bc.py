"""Golden backward-compatibility checks for provider imports.

Each test feeds a provider fixed payloads and compares the resulting `Entry`
and `Media` rows field by field with `golden/ingestion_bc.json`. That file holds
what the providers stored before entry persistence moved into
`glifestream.ingestion`. A diff here means an import now stores different data.

Re-record only for an intended data change:

    GLS_RECORD_GOLDEN=1 uv run pytest glifestream/tests/test_ingestion_bc.py
"""

import datetime
import decimal
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from glifestream.apis.atproto import AtProtoService
from glifestream.apis.flickr import FlickrService
from glifestream.apis.mastodon import MastodonService
from glifestream.apis.vimeo import VimeoService
from glifestream.apis.webfeed import WebfeedService
from glifestream.apis.youtube import YoutubeService
from glifestream.stream.models import Entry, Media, Service

GOLDEN = Path(__file__).parent / 'golden' / 'ingestion_bc.json'
RECORD = os.environ.get('GLS_RECORD_GOLDEN') == '1'
SKIPPED_FIELDS = {'id', 'service', 'date_inserted'}


def fake_save_image(url, *args, **kwargs):
    """A deterministic local thumbnail reference, as save_image would return."""
    return '[GLS-THUMBS]/%s' % hashlib.sha1(url.encode()).hexdigest()[:16]


def _value(value):
    if isinstance(value, datetime.datetime):
        # The model filled in "now" because the payload had no value.
        if abs(timezone.now() - value) < datetime.timedelta(hours=1):
            return '<now>'
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    return value


def snapshot(service: Service) -> list[dict]:
    rows = []
    for e in Entry.objects.filter(service=service).order_by('guid'):
        row = {
            f.name: _value(getattr(e, f.attname))
            for f in Entry._meta.concrete_fields
            if f.name not in SKIPPED_FIELDS
        }
        row['media'] = sorted(
            str(m.file.name) for m in Media.objects.filter(entry=e).order_by('file')
        )
        rows.append(row)
    return rows


@pytest.fixture(scope='module')
def golden():
    if RECORD:
        data: dict = {}
        yield data
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(data, indent=1, sort_keys=True) + '\n')
    else:
        yield json.loads(GOLDEN.read_text())


def check(golden, name: str, service: Service) -> None:
    rows = snapshot(service)
    if RECORD:
        golden[name] = rows
    else:
        assert rows == golden[name]


@pytest.fixture(autouse=True)
def deterministic_media():
    with patch('glifestream.stream.media.save_image', side_effect=fake_save_image):
        yield


def make_service(**kwargs) -> Service:
    s = Service(name='Golden', public=True, **kwargs)
    s.save()
    return s


def json_response(data):
    r = MagicMock()
    r.json.return_value = data
    return r


# --- webfeed ----------------------------------------------------------------

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:georss="http://www.georss.org/georss"
      xmlns:media="http://search.yahoo.com/mrss/">
  <title>Golden feed</title>
  <link href="https://blog.example/"/>
  <id>tag:blog.example,2026:feed</id>
  <updated>{updated}</updated>
  <author><name>Feed Author</name><email>feed@blog.example</email></author>
  <entry>
    <id>tag:blog.example,2026:1</id>
    <title>{title}</title>
    <link href="https://blog.example/1"/>
    <link rel="enclosure" type="image/jpeg" href="https://blog.example/1.jpg"/>
    <published>2026-03-01T10:00:00Z</published>
    <updated>{updated}</updated>
    <author><name>Alice</name><email>alice@blog.example</email>
      <uri>https://blog.example/alice</uri></author>
    <content type="html">&lt;p&gt;{body}&lt;/p&gt;&lt;script&gt;x()&lt;/script&gt;</content>
    <georss:point>52.23 21.01</georss:point>
    <media:content url="https://blog.example/1.mp4" medium="video"/>
  </entry>
  <entry>
    <id>tag:blog.example,2026:2</id>
    <title>No update time</title>
    <link href="https://blog.example/2"/>
    <published>2026-03-02T10:00:00Z</published>
    <summary>{body} summary</summary>
  </entry>
</feed>
"""


def run_webfeed(service, *, title, body, updated, force=False):
    api = WebfeedService(service, force_overwrite=force)
    api.payload = ATOM.format(title=title, body=body, updated=updated)
    api.run()
    return api


@pytest.mark.django_db
def test_webfeed_golden(golden):
    s = make_service(api='webfeed', url='https://blog.example/feed')
    run_webfeed(s, title='First', body='Hello', updated='2026-03-01T11:00:00Z')
    check(golden, 'webfeed.create', s)

    run_webfeed(s, title='Stale', body='Stale', updated='2026-03-01T11:00:00Z')
    check(golden, 'webfeed.not_newer', s)

    run_webfeed(s, title='Second', body='Changed', updated='2026-03-05T11:00:00Z')
    check(golden, 'webfeed.update', s)

    Entry.objects.filter(service=s).update(protected=True)
    run_webfeed(s, title='Third', body='Ignored', updated='2026-03-09T11:00:00Z')
    check(golden, 'webfeed.protected', s)


# --- flickr -----------------------------------------------------------------

FLICKR = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:media="http://search.yahoo.com/mrss/">
  <title>Uploads</title>
  <link rel="alternate" href="https://www.flickr.com/photos/someone/"/>
  <id>tag:flickr.com,2005:/photos/public/1</id>
  <updated>2026-03-01T10:00:00Z</updated>
  <entry>
    <title>A</title>
    <link rel="alternate" href="https://www.flickr.com/photos/someone/1/"/>
    <id>tag:flickr.com,2005:/photo/1</id>
    <published>2026-03-01T10:00:00Z</published>
    <updated>{updated}</updated>
    <media:thumbnail url="https://live.staticflickr.example/1_s.jpg" width="75" height="75"/>
    <media:content url="https://live.staticflickr.example/1.jpg" medium="image"/>
  </entry>
  <entry>
    <title>B</title>
    <link rel="alternate" href="https://www.flickr.com/photos/someone/2/"/>
    <id>tag:flickr.com,2005:/photo/2</id>
    <published>2026-03-01T10:00:00Z</published>
    <updated>{updated}</updated>
    <media:thumbnail url="https://live.staticflickr.example/2_s.jpg" width="75" height="75"/>
  </entry>
  <entry>
    <title>C</title>
    <link rel="alternate" href="https://www.flickr.com/photos/someone/3/"/>
    <link rel="image" href="https://live.staticflickr.example/3_b.jpg"/>
    <id>tag:flickr.com,2005:/photo/3</id>
    <published>2026-02-01T10:00:00Z</published>
    <updated>2026-02-01T10:00:00Z</updated>
    <media:thumbnail url="https://live.staticflickr.example/3_s.jpg" width="75" height="75"/>
  </entry>
</feed>
"""


def run_flickr(service, updated, force=False):
    api = FlickrService(service, force_overwrite=force)
    api.payload = FLICKR.format(updated=updated)
    api.run()
    return api


@pytest.mark.django_db
def test_flickr_golden(golden):
    s = make_service(api='flickr', url='http://www.flickr.com/feed')
    run_flickr(s, '2026-03-01T10:00:00Z')
    check(golden, 'flickr.create', s)

    run_flickr(s, '2026-03-01T10:00:00Z', force=True)
    check(golden, 'flickr.force', s)


# --- mastodon ---------------------------------------------------------------


def status(sid, created_at, content, **extra):
    data = {
        'id': sid,
        'created_at': created_at,
        'url': 'https://social.example/@me/%s' % sid,
        'uri': 'https://social.example/users/me/statuses/%s' % sid,
        'content': content,
        'reblog': None,
        'account': {
            'display_name': 'Me',
            'avatar_static': 'https://social.example/avatars/me.png',
        },
        'media_attachments': [],
    }
    data.update(extra)
    return data


def mastodon_payload(body):
    image = {
        'type': 'image',
        'url': 'https://social.example/media/1.png',
        'preview_url': 'https://social.example/media/1_small.png',
        'description': 'A picture',
    }
    reblogged = status('99', '2026-03-01T08:00:00.000Z', '<p>Original by other</p>') | {
        'url': 'https://other.example/@them/99',
        'account': {
            'display_name': 'Them',
            'avatar_static': 'https://other.example/avatars/them.png',
        },
    }
    return [
        status(
            '1',
            '2026-03-01T10:00:00.000Z',
            '<p>%s #tag @friend</p>' % body,
            media_attachments=[image],
        ),
        status('2', '2026-03-01T09:00:00.000Z', '<p>Reshare</p>', reblog=reblogged),
    ]


def run_mastodon(service, body, force=False):
    with patch(
        'glifestream.apis.mastodon.httpclient.get',
        return_value=json_response(mastodon_payload(body)),
    ):
        api = MastodonService(service, force_overwrite=force)
        api.run()
    return api


@pytest.mark.django_db
def test_mastodon_golden(golden):
    s = make_service(api='mastodon', url='https://social.example', user_id='42')
    run_mastodon(s, 'Hello')
    check(golden, 'mastodon.create', s)

    run_mastodon(s, 'Not newer')
    check(golden, 'mastodon.not_newer', s)

    run_mastodon(s, 'Forced', force=True)
    check(golden, 'mastodon.force', s)


# --- atproto ----------------------------------------------------------------


def bsky_post(cid, text, created_at, *, handle='me.bsky.example', avatar=None):
    return SimpleNamespace(
        cid=cid,
        uri='at://did:plc:me/app.bsky.feed.post/%s' % cid,
        record=SimpleNamespace(
            text=text, facets=None, created_at=created_at, embed=None
        ),
        author=SimpleNamespace(handle=handle, display_name='Me', avatar=avatar),
        embed=None,
    )


def run_atproto(service, text, force=False):
    repost = SimpleNamespace(
        py_type='app.bsky.feed.defs#reasonRepost',
        by=SimpleNamespace(handle='me.bsky.example', display_name='Me'),
        indexed_at='2026-03-02T10:00:00Z',
    )
    feed = [
        SimpleNamespace(
            post=bsky_post(
                'cid-1',
                text,
                '2026-03-01T10:00:00Z',
                avatar='https://cdn.bsky.example/avatar.jpg',
            ),
            reason=None,
        ),
        SimpleNamespace(
            post=bsky_post(
                'cid-2', 'Their post', '2026-03-01T09:00:00Z', handle='them.example'
            ),
            reason=repost,
        ),
    ]
    with patch('glifestream.apis.atproto._get_client_class'):
        api = AtProtoService(service, force_overwrite=force)
    api.process(cast(Any, feed))
    return api


@pytest.mark.django_db
def test_atproto_golden(golden):
    s = make_service(api='atproto', url='')
    run_atproto(s, 'Hello sky')
    check(golden, 'atproto.create', s)

    run_atproto(s, 'Forced sky', force=True)
    check(golden, 'atproto.force', s)


# --- youtube ----------------------------------------------------------------


def youtube_payload(title):
    return {
        'items': [
            {
                'id': 'pl-item-1',
                'contentDetails': {'videoId': 'vid1'},
                'snippet': {
                    'publishedAt': '2026-03-01T10:00:00.000Z',
                    'title': title,
                    'channelTitle': 'Channel',
                    'thumbnails': {
                        'medium': {
                            'url': 'https://i.ytimg.example/vid1/mq.jpg',
                            'width': 320,
                            'height': 180,
                        }
                    },
                },
            },
            {
                'id': 'pl-item-2',
                'contentDetails': {'videoId': 'vid2'},
                'snippet': {
                    'publishedAt': '2026-03-02T10:00:00Z',
                    'title': 'No thumbnails',
                    'channelTitle': 'Channel',
                },
            },
        ]
    }


def run_youtube(service, title, force=False):
    with patch(
        'glifestream.apis.youtube.httpclient.get',
        return_value=json_response(youtube_payload(title)),
    ):
        api = YoutubeService(service, force_overwrite=force)
        api.run()
    return api


@pytest.mark.django_db
def test_youtube_golden(golden):
    s = make_service(api='youtube', url='KEY:PL1')
    run_youtube(s, 'Video')
    check(golden, 'youtube.create', s)

    run_youtube(s, 'Forced video', force=True)
    check(golden, 'youtube.force', s)


# --- vimeo ------------------------------------------------------------------


def clip(clip_id, date_key, date, title):
    return {
        'id': clip_id,
        'title': title,
        'url': 'https://vimeo.com/%s' % clip_id,
        'user_name': 'Someone',
        'thumbnail_large': 'https://i.vimeo.example/%s.jpg' % clip_id,
        date_key: date,
    }


def run_vimeo(service, title, force=False):
    likes = [clip('11', 'liked_on', '2026-03-01 10:00:00', title)]
    videos = [
        clip('22', 'upload_date', '2026-03-02 10:00:00', title),
        clip('33', 'upload_date', 'not a date', 'Undated'),
    ]
    with patch(
        'glifestream.apis.vimeo.httpclient.get',
        side_effect=[json_response(likes), json_response(videos)],
    ):
        api = VimeoService(service, force_overwrite=force)
        api.run()
    return api


@pytest.mark.django_db
def test_vimeo_golden(golden):
    s = make_service(api='vimeo', url='someone')
    run_vimeo(s, 'Clip')
    check(golden, 'vimeo.create', s)

    run_vimeo(s, 'Forced clip', force=True)
    check(golden, 'vimeo.force', s)


@pytest.mark.django_db
@pytest.mark.parametrize(
    'api, run',
    [
        ('webfeed', lambda s: run_webfeed(s, title='T', body='B', updated=NOW)),
        ('flickr', lambda s: run_flickr(s, NOW)),
        ('mastodon', lambda s: run_mastodon(s, 'Hello')),
        ('atproto', lambda s: run_atproto(s, 'Hello sky')),
        ('youtube', lambda s: run_youtube(s, 'Video')),
        ('vimeo', lambda s: run_vimeo(s, 'Clip')),
    ],
)
def test_repeated_fetch_creates_nothing(api, run):
    url = 'someone' if api == 'vimeo' else 'http://feed.example/x'
    s = make_service(api=api, url=url, user_id='42')
    first = run(s).last_result
    rows = snapshot(s)

    again = run(s).last_result

    assert first.created > 0
    assert again.created == 0
    assert again.failed == first.failed
    assert snapshot(s) == rows


NOW = '2026-03-01T10:00:00Z'
