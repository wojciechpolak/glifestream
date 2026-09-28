"""
#  gLifestream Copyright (C) 2010, 2015 Wojciech Polak
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

from __future__ import annotations
import hmac
import logging
import mimetypes
import os
import re
import email
from collections.abc import Iterator
from typing import Any, IO, cast
from email.header import decode_header, make_header
from email.utils import getaddresses
from django.conf import settings
from django.core.files.uploadedfile import TemporaryUploadedFile
from django.utils.datastructures import MultiValueDict
from glifestream.apis import selfposts
from glifestream.stream.models import Service

logger = logging.getLogger(__name__)

# sysexits.h codes, which an MTA's pipe delivery reports to the sender.
EX_OK = 0
EX_SOFTWARE = 70
EX_NOPERM = 77
EX_CONFIG = 78

MIN_SECRET_LENGTH = 16

# Headers that carry the address a message was sent to. Delivered-To and
# X-Original-To, which the MTA adds, name it even when it was a Bcc.
RECIPIENT_HEADERS = ('To', 'Cc', 'Delivered-To', 'X-Original-To', 'Envelope-To')

# Parts without a file name that are still attachments, such as a photo a
# phone's mail app attaches inline.
ATTACHMENT_MAINTYPES = ('image', 'audio', 'video', 'application')


def _decoded(msg: Any, name: str) -> str:
    return str(make_header(decode_header(msg.get(name, ''))))


def _configured_secret() -> str | None:
    secret = (getattr(settings, 'EMAIL2POST_SECRET', '') or '').strip()
    if len(secret) < MIN_SECRET_LENGTH:
        return None
    return secret.lower()


def _is_secret(word: str, secret: str) -> bool:
    # Lower case, since an MTA may fold the case of a recipient address.
    return hmac.compare_digest(word.lower().encode(), secret.encode())


def _recipient_words(msg: Any) -> Iterator[str]:
    """The local part of each recipient address, and its +detail."""
    values: list[str] = []
    for header in RECIPIENT_HEADERS:
        values.extend(str(value) for value in msg.get_all(header, []))
    for _name, address in getaddresses(values):
        local = address.rsplit('@', 1)[0]
        yield local
        if '+' in local:
            yield local.split('+', 1)[1]


def _carries_secret(msg: Any, secret: str) -> bool:
    """A word of the subject, or a recipient address, is the secret."""
    words = [*_decoded(msg, 'Subject').split(), *_recipient_words(msg)]
    return any(_is_secret(word, secret) for word in words)


def _allowed_type(content_type: str) -> bool:
    """EMAIL2POST_ATTACHMENT_TYPES lists media types; "image/" or "image/*"
    stands for every image type."""
    for allowed in getattr(settings, 'EMAIL2POST_ATTACHMENT_TYPES', ()):
        allowed = allowed.strip().lower().rstrip('*')
        if content_type == allowed or (
            allowed.endswith('/') and content_type.startswith(allowed)
        ):
            return True
    return False


def _is_body(part: Any) -> bool:
    return part.get_content_type() == 'text/plain' and part.get_filename() is None


def _is_attachment(part: Any) -> bool:
    if part.is_multipart() or _is_body(part):
        return False
    return (
        part.get_filename() is not None
        or part.get_content_maintype() in ATTACHMENT_MAINTYPES
    )


def _attachment_name(part: Any) -> str:
    """The part's own file name without any directory, given an extension
    for its type when it has none the site would recognise."""
    name = os.path.basename((part.get_filename() or '').replace('\\', '/')).strip()
    if mimetypes.guess_type(name)[0] is None:
        extension = mimetypes.guess_extension(part.get_content_type()) or ''
        name = (name or 'attachment') + extension
    return name


def _keeps_attachment(part: Any, name: str) -> bool:
    """Both the type the sender declared and the one the site will serve the
    file as, which comes from its name, must be allowed."""
    served_type = mimetypes.guess_type(name)[0]
    return _allowed_type(part.get_content_type()) and (
        served_type is None or _allowed_type(served_type)
    )


def _save_attachment(part: Any, name: str) -> TemporaryUploadedFile:
    payload = part.get_payload(decode=True) or b''
    os.umask(0)
    tmp = TemporaryUploadedFile(
        name=name,
        content_type=part.get_content_type(),
        size=len(payload),
        charset=None,
    )
    tmp.write(payload)
    tmp.seek(0)
    os.chmod(cast(Any, tmp.file).name, 0o644)
    return tmp


def _text(part: Any) -> str:
    payload = part.get_payload(decode=True) or b''
    try:
        return payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
    except LookupError:
        return payload.decode('utf-8', errors='replace')


def _extract_parts(msg: Any) -> tuple[str | None, list[TemporaryUploadedFile]]:
    """The body text and every attachment worth keeping."""
    if not msg.is_multipart():
        return _text(msg), []

    content: str | None = None
    files: list[TemporaryUploadedFile] = []
    for part in msg.walk():
        if _is_attachment(part):
            name = _attachment_name(part)
            if _keeps_attachment(part, name):
                files.append(_save_attachment(part, name))
            else:
                logger.warning(
                    'email2post: dropped attachment "%s" of type %s',
                    name,
                    part.get_content_type(),
                )
        elif _is_body(part):
            content = _text(part)
    return content, files


def _parse_subject(subject: str, secret: str) -> dict[str, Any]:
    """Pull the title plus any @class, !draft and !friends-only markers."""
    args: dict[str, Any] = {}
    if not subject:
        return args

    title = ' '.join(word for word in subject.split() if not _is_secret(word, secret))

    # Mail subject may contain @foo, a selfposts' class name for which
    # this message is post to.
    m = re.search(r'(\A|\s)@(\w[\w\-]+)', title)
    if m:
        cls = m.groups()[1]
        title = re.sub(r'(\A|\s)@(\w[\w\-]+)', '', title)
        services = Service.objects.filter(cls=cls, api='selfposts').values('id')
        if len(services):
            args['sid'] = services[0]['id']

    # Mail subject may contain "!draft" literal.
    if '!draft' in title:
        title = title.replace('!draft', '').strip()
        args['draft'] = True

    # Mail subject may contain "!friends-only" literal.
    if '!friends-only' in title:
        title = title.replace('!friends-only', '').strip()
        args['friends_only'] = True

    args['title'] = title
    return args


class MailService:
    name = 'Email API'

    def __init__(self, verbose: int = 0, force_overwrite: bool = False):
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if self.verbose:
            print('%s' % self.name)

    def get_urls(self) -> tuple[str, ...]:
        return ()

    def run(self):
        pass

    def share(self, msgfile: IO[bytes]) -> int:
        secret = _configured_secret()
        if secret is None:
            logger.error(
                'email2post: EMAIL2POST_SECRET must be set, to at least %d '
                'characters, before gLifestream accepts posts by e-mail',
                MIN_SECRET_LENGTH,
            )
            return EX_CONFIG

        msg = email.message_from_binary_file(msgfile)
        if not _carries_secret(msg, secret):
            logger.warning('email2post: refused a message without the secret')
            return EX_NOPERM

        content, files = _extract_parts(msg)

        args: dict[str, Any] = _parse_subject(_decoded(msg, 'Subject'), secret)
        if content is not None:
            args['content'] = content

        if files:
            args['files'] = MultiValueDict()
            args['files'].setlist('docs', files)

        if selfposts.SelfpostsService(Service()).share(args) is None:
            return EX_SOFTWARE
        return EX_OK
