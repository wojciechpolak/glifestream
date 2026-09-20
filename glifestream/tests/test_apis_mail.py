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

import io
import pytest
from unittest.mock import patch

from django.test import override_settings

from glifestream.apis.mail import MailService
from glifestream.stream.models import Entry, Media, Service


@pytest.fixture(autouse=True)
def no_sender_check(settings):
    """Settings ship a From check; the tests that care set their own."""
    settings.EMAIL2POST_CHECK = {}


@pytest.fixture
def notes(db):
    return Service.objects.create(
        name='Notes', api='selfposts', cls='notes', url='', public=True
    )


def message(**headers):
    body = headers.pop('body', 'Hello from e-mail')
    lines = ''.join('%s: %s\n' % (k.replace('_', '-'), v) for k, v in headers.items())
    return io.StringIO('%s\n%s\n' % (lines, body))


def multipart(parts, **headers):
    boundary = 'BOUNDARY'
    lines = ''.join('%s: %s\n' % (k.replace('_', '-'), v) for k, v in headers.items())
    body = ''
    for content_type, disposition, payload in parts:
        body += '--%s\n' % boundary
        body += 'Content-Type: %s\n' % content_type
        if disposition:
            body += 'Content-Disposition: %s\n' % disposition
        body += '\n%s\n' % payload
    body += '--%s--\n' % boundary
    return io.StringIO(
        '%sMIME-Version: 1.0\n'
        'Content-Type: multipart/mixed; boundary="%s"\n\n%s' % (lines, boundary, body)
    )


@pytest.mark.django_db
def test_share_creates_an_entry_from_a_plain_message(notes):
    assert MailService().share(message(Subject='A note', body='Body text')) == 0

    entry = Entry.objects.get()
    assert entry.title == 'A note'
    assert 'Body text' in entry.content


@pytest.mark.django_db
def test_share_accepts_a_message_with_no_subject(notes):
    """A subject-less mail used to raise KeyError before it reached the post."""
    assert MailService().share(message(body='No subject here')) == 0

    assert 'No subject here' in Entry.objects.get().content


@override_settings(EMAIL2POST_CHECK={'From': 'trusted@example.com'})
@pytest.mark.django_db
def test_share_refuses_a_sender_that_does_not_match(notes):
    result = MailService().share(message(From='stranger@example.com', Subject='Hi'))

    assert result == 77  # EX_NOPERM
    assert not Entry.objects.exists()


@override_settings(EMAIL2POST_CHECK={'From': 'trusted@example.com'})
@pytest.mark.django_db
def test_share_accepts_a_sender_that_matches(notes):
    result = MailService().share(
        message(From='Someone <trusted@example.com>', Subject='Hi')
    )

    assert result == 0
    assert Entry.objects.exists()


@pytest.mark.django_db
def test_share_routes_an_at_class_subject_to_that_service(notes):
    photos = Service.objects.create(
        name='Photos', api='selfposts', cls='photos', url='', public=True
    )

    MailService().share(message(Subject='Sunset @photos', body='A picture'))

    entry = Entry.objects.get()
    assert entry.service == photos
    assert entry.title == 'Sunset'


@pytest.mark.django_db
def test_share_ignores_an_at_class_that_matches_no_service(notes):
    MailService().share(message(Subject='Hello @nowhere'))

    assert Entry.objects.get().service == notes


@pytest.mark.django_db
def test_share_honours_the_draft_marker(notes):
    MailService().share(message(Subject='Half done !draft'))

    entry = Entry.objects.get()
    assert entry.draft is True
    assert entry.title == 'Half done'


@pytest.mark.django_db
def test_share_honours_the_friends_only_marker(notes):
    MailService().share(message(Subject='Just for you !friends-only'))

    entry = Entry.objects.get()
    assert entry.friends_only is True
    assert entry.title == 'Just for you'


@pytest.mark.django_db
def test_share_decodes_an_encoded_subject(notes):
    MailService().share(message(Subject='=?utf-8?q?Caf=C3=A9?='))

    assert Entry.objects.get().title == 'Café'


@pytest.mark.django_db
def test_share_reads_the_text_part_of_a_multipart_message(notes):
    msgfile = multipart(
        [
            ('text/html', None, '<p>ignored</p>'),
            ('text/plain', None, 'The real body'),
        ],
        Subject='Multipart',
    )

    MailService().share(msgfile)

    assert 'The real body' in Entry.objects.get().content


@pytest.mark.django_db
def test_share_keeps_attachments(notes):
    msgfile = multipart(
        [
            ('text/plain', None, 'See attached'),
            ('application/pdf', 'attachment; filename="report.pdf"', 'PDFDATA'),
        ],
        Subject='With a file',
    )

    with patch('glifestream.apis.selfposts.media.downsave_uploaded_image'):
        MailService().share(msgfile)

    entry = Entry.objects.get()
    assert 'report.pdf' in entry.content
    assert Media.objects.filter(entry=entry).count() == 1


@pytest.mark.django_db
def test_share_treats_a_named_text_part_as_an_attachment(notes):
    msgfile = multipart(
        [('text/plain', 'attachment; filename="notes.txt"', 'attached text')],
        Subject='Only an attachment',
    )

    MailService().share(msgfile)

    entry = Entry.objects.get()
    assert 'notes.txt' in entry.content
    assert 'attached text' not in entry.content


@pytest.mark.django_db
def test_mail_service_is_otherwise_inert(capsys):
    api = MailService(verbose=1)

    assert 'Email API' in capsys.readouterr().out
    assert api.get_urls() == ()
    assert api.run() is None
