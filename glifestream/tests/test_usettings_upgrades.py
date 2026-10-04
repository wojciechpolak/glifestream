"""The settings pages that review, apply and revert entry upgrades."""

from __future__ import annotations

import re
from unittest.mock import patch
from urllib.parse import urlencode

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from glifestream import upgrades
from glifestream.filters import music
from glifestream.stream.models import Entry, EntryUpgrade, Service

OLD = (
    '<table class="vc"><tr><td><div id="youtube-abc" class="play-video">'
    '<a href="https://www.youtube.com/watch?v=abc" rel="nofollow">'
    '<img src="[GLS-THUMBS]/afa533f8.jpg" width="200" height="150" alt="YouTube Video" />'
    '</a><div class="playbutton"></div></div></td></tr></table>'
)
NEW_THUMB = '[GLS-THUMBS]/ad97b17f.webp'


@pytest.fixture(autouse=True)
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.APP_THUMBNAIL_FORMAT = 'WEBP'
    thumb = tmp_path / 'thumbs' / 'a' / 'ad97b17f.webp'
    thumb.parent.mkdir(parents=True)
    thumb.write_bytes(b'thumb')
    return tmp_path


@pytest.fixture
def staff_client(client, db):
    User.objects.create_user(username='staff', password='password', is_staff=True)
    client.login(username='staff', password='password')
    return client


@pytest.fixture
def entry(db):
    service = Service.objects.create(name='YouTube', api='youtube', public=True)
    return Entry.objects.create(
        service=service,
        guid='tag:youtube.com,2008:video:abc',
        title='Old Video',
        link='http://www.youtube.com/watch?v=abc',
        content=OLD,
        protected=True,
    )


@pytest.fixture
def new_thumbnail():
    with patch('glifestream.apis.youtube.media.save_image', return_value=NEW_THUMB):
        yield


def review_url(**query):
    url = reverse('usettings-upgrade-review', args=['youtube'])
    if query:
        url += '?' + '&'.join('%s=%s' % kv for kv in query.items())
    return url


def search(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.S)
    assert m is not None, pattern
    return m.group(1)


def token_of(body: str) -> str:
    return search(r'name="token" value="([^"]+)"', body)


@pytest.mark.django_db
def test_the_pages_are_for_staff_only(client, entry):
    for url in (reverse('usettings-upgrades'), review_url()):
        assert client.get(url).status_code == 302
    User.objects.create_user(username='user', password='password')
    client.login(username='user', password='password')
    for url in (reverse('usettings-upgrades'), review_url()):
        assert client.get(url).status_code == 403
    apply_url = reverse('usettings-upgrade-apply', args=['youtube'])
    assert client.post(apply_url, {'token': 'x'}).status_code == 403


@pytest.mark.django_db
def test_overview_counts_the_entries_of_each_provider(staff_client, entry):
    body = staff_client.get(reverse('usettings-upgrades')).content.decode()

    assert 'class="active">Upgrades<' in body
    row = search(r'data-upgrader="youtube">(.*?)</tr>', body)
    assert '<td class="count pending">1</td>' in row
    assert review_url() in row
    assert 'data-upgrader="vimeo"' in body


@pytest.mark.django_db
def test_review_shows_the_entry_now_and_after(staff_client, entry, new_thumbnail):
    body = staff_client.get(review_url()).content.decode()

    compare = search(
        r'<div id="stream" class="upgrade-compare">(.*?)<div class="upgrade-actions">',
        body,
    )
    articles = re.findall(r'<article\b[^>]*>.*?</article>', compare, re.S)
    assert len(articles) == 2
    before, after = articles
    assert 'afa533f8.jpg' in before and 'class="vc"' in before
    assert 'ad97b17f.webp' in after and 'class="vc"' not in after
    assert 'data-id="youtube-abc"' in after
    # Ids stay unique on the page.
    assert 'id="entry-%d"' % entry.pk in before
    assert 'id="entry-' not in after and 'id="shareit-' not in after
    # The public view: no entry controls.
    assert 'entry-controls' not in compare
    assert '1 of 1' in body
    assert 'Protected' in body
    assert '-http://www.youtube.com/watch?v=abc' in body
    assert 'name="token"' in body


@pytest.mark.django_db
def test_review_without_a_proposal_offers_only_skip(staff_client, entry):
    with patch(
        'glifestream.apis.youtube.media.save_image', side_effect=lambda u, **k: u
    ):
        body = staff_client.get(review_url()).content.decode()

    assert 'This entry cannot be upgraded.' in body
    assert 'YouTube has no thumbnail' in body
    assert 'name="token"' not in body
    assert reverse('usettings-upgrade-skip', args=['youtube']) in body


@pytest.mark.django_db
def test_review_of_an_unknown_upgrader_is_not_found(staff_client):
    url = reverse('usettings-upgrade-review', args=['nosuch'])

    assert staff_client.get(url).status_code == 404


@pytest.mark.django_db
def test_apply_then_revert(staff_client, entry, new_thumbnail):
    token = token_of(staff_client.get(review_url()).content.decode())
    apply_url = reverse('usettings-upgrade-apply', args=['youtube'])

    assert staff_client.get(apply_url).status_code == 405
    response = staff_client.post(apply_url, {'token': token, 'entry': entry.pk})

    upgrade = EntryUpgrade.objects.get()
    assert response.status_code == 302
    assert response['Location'] == review_url(after=entry.pk, done=upgrade.pk)
    entry.refresh_from_db()
    assert 'ad97b17f.webp' in entry.content
    body = staff_client.get(response['Location']).content.decode()
    assert 'Applied to entry #%d.' % entry.pk in body
    assert 'All YouTube entries are up to date.' in body

    revert_url = reverse('usettings-upgrade-revert', args=[upgrade.pk])
    response = staff_client.post(revert_url, follow=True)

    entry.refresh_from_db()
    assert entry.content == OLD
    assert 'Reverted.' in response.content.decode()


@pytest.mark.django_db
def test_apply_of_a_stale_preview_saves_nothing(staff_client, entry, new_thumbnail):
    token = token_of(staff_client.get(review_url()).content.decode())
    Entry.objects.filter(pk=entry.pk).update(title='Edited', content=OLD + ' ')

    response = staff_client.post(
        reverse('usettings-upgrade-apply', args=['youtube']),
        {'token': token, 'entry': entry.pk},
        follow=True,
    )

    assert 'The entry changed after its preview was shown.' in response.content.decode()
    assert not EntryUpgrade.objects.exists()
    entry.refresh_from_db()
    assert entry.content == OLD + ' '


@pytest.mark.django_db
def test_skip_and_offer_again(staff_client, entry, new_thumbnail):
    response = staff_client.post(
        reverse('usettings-upgrade-skip', args=['youtube']), {'entry': entry.pk}
    )

    assert response['Location'] == review_url(after=entry.pk)
    assert EntryUpgrade.objects.get().status == EntryUpgrade.STATUS_SKIPPED
    assert upgrades.pending(upgrades.UPGRADERS['youtube']) == []

    staff_client.post(reverse('usettings-upgrade-requeue', args=['youtube']))

    assert not EntryUpgrade.objects.exists()
    entry.refresh_from_db()
    assert entry.content == OLD


@pytest.mark.django_db
def test_decide_later_moves_on_to_the_next_entry(staff_client, entry, new_thumbnail):
    second = Entry.objects.create(
        service=entry.service,
        guid='tag:youtube.com,2008:video:def',
        title='Next Video',
        link='https://www.youtube.com/watch?v=def',
        content=OLD.replace('abc', 'def'),
    )

    body = staff_client.get(review_url(after=entry.pk)).content.decode()

    assert '2 of 2' in body
    assert '#%d' % second.pk in body
    body = staff_client.get(review_url(after=second.pk)).content.decode()
    assert 'No more entries after this one.' in body


@pytest.mark.django_db
def test_revert_from_the_review_shows_the_entry_again(
    staff_client, entry, new_thumbnail
):
    token = token_of(staff_client.get(review_url()).content.decode())
    staff_client.post(
        reverse('usettings-upgrade-apply', args=['youtube']),
        {'token': token, 'entry': entry.pk},
    )
    upgrade = EntryUpgrade.objects.get()

    response = staff_client.post(
        reverse('usettings-upgrade-revert', args=[upgrade.pk]), {'next': 'review'}
    )

    assert response['Location'] == review_url(entry=entry.pk)
    body = staff_client.get(response['Location']).content.decode()
    assert '#%d' % entry.pk in body and 'name="token"' in body


CURRENT_BUT_ID = (
    '<div id="youtube-%s" class="play-video">'
    '<a href="https://www.youtube.com/watch?v=%s" rel="nofollow">'
    '<img src="[GLS-THUMBS]/ad97b17f.webp" width="320" height="180" alt="YouTube Video" />'
    '</a><div class="playbutton"></div></div>'
)


@pytest.fixture
def markup_entries(entry):
    """Two entries whose upgrade only turns their id into a data-id."""
    return [
        Entry.objects.create(
            service=entry.service,
            guid='tag:youtube.com,2008:video:%s' % vid,
            title='Video %s' % vid,
            link='https://www.youtube.com/watch?v=%s' % vid,
            content=CURRENT_BUT_ID % (vid, vid),
        )
        for vid in ('m1', 'm2')
    ]


@pytest.mark.django_db
def test_markup_only_is_offered_and_applied_as_a_batch(
    staff_client, entry, markup_entries
):
    overview = staff_client.get(reverse('usettings-upgrades')).content.decode()
    confirm_url = reverse('usettings-upgrade-markup-only', args=['youtube'])
    assert confirm_url in overview
    assert 'Apply 2 where only the markup changes' in overview
    review = staff_client.get(review_url()).content.decode()
    assert confirm_url in review

    with patch('glifestream.apis.youtube.media.save_image', side_effect=AssertionError):
        body = staff_client.get(confirm_url).content.decode()

    listed = re.findall(r'<tr data-entry="(\d+)">', body)
    assert listed == [str(e.pk) for e in markup_entries]
    assert 'markup' in search(r'<tr data-entry="\d+">(.*?)</tr>', body)
    assert len(re.findall(r'<article\b', body)) == 2
    assert 'Apply to all 2 entries' in body

    response = staff_client.post(
        reverse('usettings-upgrade-apply-markup-only', args=['youtube']),
        {'token': token_of(body)},
        follow=True,
    )

    body = response.content.decode()
    assert 'Applied to 2 entries.' in body
    batch = search(r'<tr data-batch="([0-9a-f]+)">', body)
    assert 'A batch of 2 entries' in body
    for e in markup_entries:
        e.refresh_from_db()
        assert 'data-id="youtube-m' in e.content
    entry.refresh_from_db()
    assert entry.content == OLD

    response = staff_client.post(
        reverse('usettings-upgrade-revert-batch', args=[batch]), follow=True
    )

    assert 'Reverted 2 entries.' in response.content.decode()
    for e in markup_entries:
        e.refresh_from_db()
        assert e.content.startswith('<div id="youtube-m')


@pytest.mark.django_db
def test_markup_only_with_nothing_to_offer_goes_back(staff_client, entry):
    response = staff_client.get(
        reverse('usettings-upgrade-markup-only', args=['youtube']), follow=True
    )

    assert response.redirect_chain[-1][0] == reverse('usettings-upgrades')
    assert 'No waiting entry changes only its markup.' in response.content.decode()


MUSIC_POST = (
    '<p><span id="thesixtyone-art-x1" class="play-audio">'
    '<a href="http://www.thesixtyone.com/s/x1/" rel="nofollow">Brave Men</a></span>'
    ' by The Impossible Shoelace</p>'
)


@pytest.fixture
def music_entry(db):
    service = Service.objects.create(name='Music', api='selfposts', cls='music')
    return Entry.objects.create(
        service=service,
        guid='tag:example,2009:music',
        title='Brave Men',
        link='http://www.thesixtyone.com/s/x1/',
        content=MUSIC_POST,
    )


def music_url(**query):
    url = reverse('usettings-upgrade-review', args=['music'])
    return url + ('?' + urlencode(query) if query else '')


@pytest.mark.django_db
def test_music_review_asks_the_owner_and_starts_from_a_guess(staff_client, music_entry):
    body = staff_client.get(music_url()).content.decode()

    form = search(r'<form method="get"[^>]*class="upgrade-fields">(.*?)</form>', body)
    assert 'name="entry" value="%d"' % music_entry.pk in form
    assert 'name="artist" value="The Impossible Shoelace"' in form
    assert 'name="title" value="Brave Men"' in form
    assert 'name="youtube" value=""' in form
    assert (
        'https://www.youtube.com/results?search_query=The+Impossible+Shoelace+Brave+Men'
        in form
    )
    before, after = re.findall(r'<article\b[^>]*>.*?</article>', body, re.S)
    assert 'thesixtyone' in before
    assert '<div class="music-card">' in after
    assert 'name="token"' in body


@pytest.mark.django_db
def test_music_preview_shows_what_the_owner_entered(staff_client, music_entry):
    yt_thumb = '[GLS-THUMBS]/ad97b17f.webp'
    query = {
        'entry': music_entry.pk,
        'artist': 'Shoelace',
        'title': 'Brave Men',
        'youtube': 'https://youtu.be/vid1',
        'cover': '',
    }
    with patch('glifestream.filters.music.media.save_image', return_value=yt_thumb):
        with patch(
            'glifestream.filters.music._local_cover',
            return_value=music.Cover(yt_thumb, 320, 180),
        ):
            body = staff_client.get(music_url(**query)).content.decode()

    assert 'name="artist" value="Shoelace"' in body
    assert 'data-id="youtube-vid1"' in body

    response = staff_client.post(
        reverse('usettings-upgrade-apply', args=['music']),
        {'token': token_of(body), 'entry': music_entry.pk},
    )

    assert response.status_code == 302
    music_entry.refresh_from_db()
    assert 'data-id="youtube-vid1"' in music_entry.content
    assert '<span class="music-artist">Shoelace</span>' in music_entry.content


@pytest.mark.django_db
def test_music_review_without_the_artist_keeps_the_form(staff_client, music_entry):
    body = staff_client.get(
        music_url(entry=music_entry.pk, artist='', title='Brave Men')
    ).content.decode()

    assert 'Fill in the fields above to see B.' in body
    assert 'Enter the artist and the title of the track.' in body
    assert 'class="upgrade-fields"' in body
    assert 'name="token"' not in body
