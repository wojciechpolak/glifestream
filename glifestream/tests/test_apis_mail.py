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

from glifestream.apis.mail import MailService
from glifestream.stream.models import Entry, Media, Service
from glifestream.worker import cli


SECRET = '0123456789abcdef0123'
SECRET_ADDRESS = 'gls+%s@example.com' % SECRET


@pytest.fixture(autouse=True)
def email2post_secret(settings):
    settings.EMAIL2POST_SECRET = SECRET


@pytest.fixture
def notes(db):
    return Service.objects.create(
        name='Notes', api='selfposts', cls='notes', url='', public=True
    )


def header_lines(headers):
    """The headers, sent to the secret address unless a test says otherwise."""
    headers.setdefault('To', SECRET_ADDRESS)
    return ''.join(
        '%s: %s\n' % (k.replace('_', '-'), v)
        for k, v in headers.items()
        if v is not None
    )


def message(**headers):
    body = headers.pop('body', 'Hello from e-mail')
    if isinstance(body, str):
        body = body.encode('utf-8')
    return io.BytesIO(header_lines(headers).encode('ascii') + b'\n' + body + b'\n')


def multipart(parts, **headers):
    boundary = 'BOUNDARY'
    lines = header_lines(headers)
    body = ''
    for content_type, disposition, payload in parts:
        body += '--%s\n' % boundary
        body += 'Content-Type: %s\n' % content_type
        if disposition:
            body += 'Content-Disposition: %s\n' % disposition
        body += '\n%s\n' % payload
    body += '--%s--\n' % boundary
    return io.BytesIO(
        (
            '%sMIME-Version: 1.0\n'
            'Content-Type: multipart/mixed; boundary="%s"\n\n%s'
            % (lines, boundary, body)
        ).encode('utf-8')
    )


@pytest.mark.django_db
def test_share_creates_an_entry_from_a_plain_message(notes):
    assert MailService().share(message(Subject='A note', body='Body text')) == 0

    entry = Entry.objects.get()
    assert entry.title == 'A note'
    assert entry.content == '<p>Body text</p>'


@pytest.mark.django_db
def test_share_decodes_the_body_in_its_charset(notes):
    """The body was once posted as the repr of its bytes: <p>b'Za\\xc5...'</p>."""
    msgfile = message(
        Subject='Charset',
        Content_Type='text/plain; charset=iso-8859-2',
        Content_Transfer_Encoding='8bit',
        body='Zażółć gęślą jaźń'.encode('iso-8859-2'),
    )

    MailService().share(msgfile)

    assert Entry.objects.get().content == '<p>Zażółć gęślą jaźń</p>'


@pytest.mark.django_db
def test_share_decodes_a_body_in_an_unknown_charset_as_utf8(notes):
    msgfile = message(
        Subject='Charset',
        Content_Type='text/plain; charset=x-nonexistent',
        Content_Transfer_Encoding='8bit',
        body='Zażółć',
    )

    MailService().share(msgfile)

    assert Entry.objects.get().content == '<p>Zażółć</p>'


@pytest.mark.django_db
def test_share_accepts_a_message_with_no_subject(notes):
    """A subject-less mail used to raise KeyError before it reached the post."""
    assert MailService().share(message(body='No subject here')) == 0

    assert 'No subject here' in Entry.objects.get().content


@pytest.mark.parametrize('secret', ['', 'short-secret'])
@pytest.mark.django_db
def test_share_posts_nothing_until_a_long_enough_secret_is_set(
    notes, settings, secret, caplog
):
    settings.EMAIL2POST_SECRET = secret

    result = MailService().share(message(To='gls+%s@example.com' % secret))

    assert result == 78  # EX_CONFIG
    assert not Entry.objects.exists()
    assert 'EMAIL2POST_SECRET must be set' in caplog.text


@pytest.mark.django_db
def test_share_refuses_a_message_without_the_secret(notes, caplog):
    """The From header, which anyone can forge, earns no trust."""
    result = MailService().share(
        message(From='Owner <owner@example.com>', To='gls@example.com', Subject='Hi')
    )

    assert result == 77  # EX_NOPERM
    assert not Entry.objects.exists()
    assert 'without the secret' in caplog.text


@pytest.mark.parametrize(
    'headers',
    [
        {'To': 'Stream <gls+%s@example.com>' % SECRET},
        {'To': 'friend@example.com', 'Cc': 'gls+%s@example.com' % SECRET},
        # A Bcc: only the MTA's own header names the address.
        {'To': 'friend@example.com', 'Delivered-To': 'gls+%s@example.com' % SECRET},
        {'To': None, 'X-Original-To': '%s@example.com' % SECRET},
        # An MTA may fold an address to lower case, or a user type it upper.
        {'To': 'GLS+%s@EXAMPLE.COM' % SECRET.upper()},
    ],
    ids=['to', 'cc', 'delivered-to', 'local-part', 'case'],
)
@pytest.mark.django_db
def test_share_accepts_the_secret_in_a_recipient_address(notes, headers):
    assert MailService().share(message(Subject='Hi', **headers)) == 0

    assert Entry.objects.get().title == 'Hi'


@pytest.mark.django_db
def test_share_accepts_the_secret_in_the_subject_and_leaves_it_out_of_the_title(
    notes,
):
    msgfile = message(To='gls@example.com', Subject='Morning %s walk' % SECRET)

    assert MailService().share(msgfile) == 0

    assert Entry.objects.get().title == 'Morning walk'


@pytest.mark.parametrize(
    'headers',
    [
        {'Subject': 'x%s' % SECRET},
        {'To': 'gls+x%s@example.com' % SECRET},
        {'To': 'gls@%s.example.com' % SECRET},
    ],
    ids=['subject-substring', 'address-substring', 'domain'],
)
@pytest.mark.django_db
def test_share_needs_the_secret_as_a_whole_word(notes, headers):
    headers.setdefault('To', 'gls@example.com')

    assert MailService().share(message(**headers)) == 77

    assert not Entry.objects.exists()


@pytest.mark.django_db
def test_share_reports_a_post_that_could_not_be_saved(notes):
    """The sender gets a bounce rather than a post lost without a word."""
    with patch(
        'glifestream.apis.mail.selfposts.SelfpostsService.share', return_value=None
    ):
        assert MailService().share(message(Subject='Lost')) == 70


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


@pytest.mark.parametrize(
    'content_type, disposition',
    [
        ('text/html', 'attachment; filename="page.html"'),
        ('image/svg+xml', 'attachment; filename="logo.svg"'),
        ('application/zip', 'attachment; filename="bundle.zip"'),
        # Declared a picture, but the site would serve it by its name.
        ('image/jpeg', 'attachment; filename="photo.html"'),
    ],
    ids=['html', 'svg', 'zip', 'misnamed'],
)
@pytest.mark.django_db
def test_share_drops_an_attachment_of_a_type_not_allowed(
    notes, content_type, disposition, caplog
):
    msgfile = multipart(
        [
            ('text/plain', None, 'Still posted'),
            (content_type, disposition, 'DATA'),
        ],
        Subject='Dropped file',
    )

    assert MailService().share(msgfile) == 0

    entry = Entry.objects.get()
    assert entry.content == '<p>Still posted</p>'
    assert not Media.objects.filter(entry=entry).exists()
    assert 'dropped attachment' in caplog.text


@pytest.mark.django_db
def test_share_keeps_an_attachment_type_the_settings_allow(notes, settings):
    settings.EMAIL2POST_ATTACHMENT_TYPES = ['application/*']
    msgfile = multipart(
        [('application/zip', 'attachment; filename="bundle.zip"', 'DATA')],
        Subject='Archive',
    )

    MailService().share(msgfile)

    assert str(Media.objects.get().file.name).endswith('/bundle.zip')


@pytest.mark.django_db
def test_share_keeps_only_the_file_name_of_an_attachment(notes):
    msgfile = multipart(
        [('application/pdf', 'attachment; filename="..\\..\\report.pdf"', 'DATA')],
        Subject='Path',
    )

    MailService().share(msgfile)

    name = str(Media.objects.get().file.name)
    assert name.startswith('upload/')
    assert name.endswith('/report.pdf')
    assert '..' not in name


@pytest.mark.django_db
def test_share_names_a_nameless_picture_by_its_type(notes):
    msgfile = multipart([('image/jpeg', 'inline', 'JPEGDATA')], Subject='Photo')

    with patch(
        'glifestream.apis.selfposts.media.downsave_uploaded_image',
        return_value=('thumb.jpg', 'orig.jpg'),
    ):
        MailService().share(msgfile)

    assert str(Media.objects.get().file.name).endswith('/attachment.jpg')


@pytest.mark.django_db
def test_worker_email2post_posts_the_message_on_stdin(notes, monkeypatch):
    """The path an MTA's pipe takes: worker.py --email2post."""
    # Text read from stdin once escaped what it could not map: Za\\u017c...
    stdin = message(
        Subject='Piped',
        Content_Type='text/plain; charset=utf-8',
        Content_Transfer_Encoding='8bit',
        body='Zażółć',
    )
    monkeypatch.setattr('sys.stdin', io.TextIOWrapper(stdin, encoding='ascii'))

    command = cli.parse_legacy_command(['--email2post'])
    assert cli.execute_command(command, prog_name='worker.py') == 0

    entry = Entry.objects.get()
    assert entry.title == 'Piped'
    assert entry.content == '<p>Zażółć</p>'


@pytest.mark.django_db
def test_mail_service_is_otherwise_inert(capsys):
    api = MailService(verbose=1)

    assert 'Email API' in capsys.readouterr().out
    assert api.get_urls() == ()
    assert api.run() is None
