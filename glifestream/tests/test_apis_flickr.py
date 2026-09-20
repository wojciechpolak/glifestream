"""
#  gLifestream Copyright (C) 2026 Wojciech Polak
#
#  This program is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License as published by the
#  Free Software Foundation; either version 3 of the License, or (at your
#  option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import datetime
import pytest
from types import SimpleNamespace
from unittest.mock import patch

import feedparser

from glifestream.apis.flickr import FlickrService, filter_title
from glifestream.stream.models import Entry

UTC = datetime.timezone.utc


def photo(photo_id, updated='2026-03-22T17:00:00Z', **extra):
    """A feedparser-ish entry: Flickr's RSS as the parser hands it over."""
    ent = feedparser.FeedParserDict(
        id=photo_id,
        link='https://flickr.com/photo/%s' % photo_id,
        updated=updated,
        links=[],
    )
    ent.update(extra)
    return ent


def thumbnail(url='https://flickr.example/t.jpg', width='75', height='75'):
    return [{'url': url, 'width': width, 'height': height}]


@pytest.fixture
def flickr(service):
    service.api = 'flickr'
    service.url = '12345@N00'
    service.link = 'https://flickr.com/photos/me'
    service.save()
    api = FlickrService(service)
    api.fp = SimpleNamespace(feed=feedparser.FeedParserDict())
    return api


@pytest.mark.django_db
def test_get_urls_builds_a_public_photos_feed(flickr):
    assert flickr.get_urls() == (
        'http://api.flickr.com/services/feeds/photos_public.gne?id=12345@N00&format=rss_200',
    )


@pytest.mark.django_db
def test_get_urls_passes_an_explicit_url_through(flickr):
    flickr.service.url = 'http://example.com/custom.rss'

    assert flickr.get_urls() == ('http://example.com/custom.rss',)


@pytest.mark.django_db
def test_process_groups_photos_sharing_a_timestamp(flickr):
    entries = [
        photo('1', media_thumbnail=thumbnail('https://flickr.example/1.jpg')),
        photo('2', media_thumbnail=thumbnail('https://flickr.example/2.jpg')),
    ]

    with patch(
        'glifestream.apis.flickr.media.save_image', side_effect=lambda url, **kw: url
    ):
        flickr.process(entries)

    entry = Entry.objects.get(service=flickr.service)
    assert entry.guid == 'tag:flickr.com,2004:/photo/1'
    assert entry.idata == 'grouped'
    assert entry.title == 'Posted Photos'
    assert entry.link == 'https://flickr.com/photos/me'
    assert 'https://flickr.example/1.jpg' in entry.content
    assert 'https://flickr.example/2.jpg' in entry.content


@pytest.mark.django_db
def test_process_keeps_separate_timestamps_apart(flickr):
    entries = [
        photo('1', updated='2026-03-22T17:00:00Z'),
        photo('2', updated='2026-03-22T18:00:00Z'),
    ]

    flickr.process(entries)

    assert Entry.objects.filter(service=flickr.service).count() == 2
    assert not Entry.objects.filter(idata='grouped').exists()


@pytest.mark.django_db
def test_process_saves_thumbnails_locally_only_for_a_public_service(flickr):
    flickr.service.public = False
    flickr.service.save()

    with patch('glifestream.apis.flickr.media.save_image') as save_image:
        flickr.process([photo('1', media_thumbnail=thumbnail())])

    save_image.assert_not_called()
    assert 'https://flickr.example/t.jpg' in Entry.objects.get().content


@pytest.mark.django_db
def test_process_collects_media_content_into_the_mblob(flickr):
    media_content = [{'url': 'https://flickr.example/big.jpg', 'medium': 'image'}]

    flickr.process([photo('1', media_content=media_content)])

    assert 'flickr.example/big.jpg' in Entry.objects.get().mblob


@pytest.mark.django_db
def test_process_uses_the_published_date_when_there_is_one(flickr):
    ent = photo(
        '1',
        published_parsed=(2026, 3, 22, 17, 0, 0, 0, 0, 0),
        updated_parsed=(2026, 3, 22, 18, 0, 0, 0, 0, 0),
    )

    flickr.process([ent])

    entry = Entry.objects.get()
    assert entry.date_published == datetime.datetime(2026, 3, 22, 17, 0, tzinfo=UTC)
    assert entry.date_updated == datetime.datetime(2026, 3, 22, 18, 0, tzinfo=UTC)


@pytest.mark.django_db
def test_process_falls_back_to_the_updated_date(flickr):
    flickr.process([photo('1', updated_parsed=(2026, 3, 22, 18, 0, 0, 0, 0, 0))])

    entry = Entry.objects.get()
    assert entry.date_published == datetime.datetime(2026, 3, 22, 18, 0, tzinfo=UTC)


@pytest.mark.django_db
def test_process_skips_an_entry_that_has_not_changed(flickr):
    ent = photo('1', updated_parsed=(2026, 3, 22, 17, 0, 0, 0, 0, 0))
    flickr.process([ent])
    Entry.objects.filter(service=flickr.service).update(title='Edited by hand')

    flickr.process([ent])

    assert Entry.objects.get().title == 'Edited by hand'


@pytest.mark.django_db
def test_force_overwrite_rewrites_an_unchanged_entry(flickr):
    ent = photo('1', updated_parsed=(2026, 3, 22, 17, 0, 0, 0, 0, 0))
    flickr.process([ent])
    Entry.objects.filter(service=flickr.service).update(title='Edited by hand')

    flickr.force_overwrite = True
    flickr.process([ent])

    assert Entry.objects.get().title == 'Posted Photos'


@pytest.mark.django_db
def test_process_never_touches_a_protected_entry(flickr):
    ent = photo('1')
    flickr.process([ent])
    Entry.objects.filter(service=flickr.service).update(
        protected=True, title='Hands off'
    )

    flickr.force_overwrite = True
    flickr.process([ent])

    assert Entry.objects.get().title == 'Hands off'


@pytest.mark.django_db
def test_process_prefers_the_feed_image_for_the_avatar(flickr):
    flickr.fp.feed = feedparser.FeedParserDict(
        image=feedparser.FeedParserDict(href='https://flickr.example/avatar.jpg')
    )

    with patch(
        'glifestream.apis.flickr.media.save_image', side_effect=lambda url, **kw: url
    ):
        flickr.process([photo('1')])

    assert Entry.objects.get().link_image == 'https://flickr.example/avatar.jpg'


@pytest.mark.django_db
def test_process_falls_back_to_an_entry_image_link(flickr):
    ent = photo('1')
    ent['links'] = [
        SimpleNamespace(rel='alternate', href='https://flickr.example/page'),
        SimpleNamespace(rel='image', href='https://flickr.example/from-link.jpg'),
    ]

    with patch(
        'glifestream.apis.flickr.media.save_image', side_effect=lambda url, **kw: url
    ):
        flickr.process([ent])

    assert Entry.objects.get().link_image == 'https://flickr.example/from-link.jpg'


@pytest.mark.django_db
def test_process_survives_an_entry_it_cannot_save(flickr):
    with patch.object(Entry, 'save', side_effect=Exception('db is upset')):
        flickr.process([photo('1')])

    assert not Entry.objects.exists()


@pytest.mark.django_db
def test_process_is_chatty_when_verbose(flickr, capsys):
    flickr.verbose = 1

    flickr.process([photo('7')])

    assert 'ID: 7' in capsys.readouterr().out


def test_filter_title_names_one_photo_or_many():
    assert 'Photos' in filter_title(Entry(idata='grouped'))
    assert 'a Photo' in filter_title(Entry(idata=''))
