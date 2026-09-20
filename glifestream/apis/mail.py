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
import os
import re
import email
from typing import Any, IO, cast
from email.header import decode_header, make_header
from django.conf import settings
from django.core.files.uploadedfile import TemporaryUploadedFile
from django.utils.datastructures import MultiValueDict
from glifestream.apis import selfposts
from glifestream.stream.models import Service


ATTACHMENT_PREFIXES = ('image/', 'audio/', 'video/', 'application/')


def _sender_is_allowed(msg: Any) -> bool:
    """EMAIL2POST_CHECK maps a header name to a substring it must contain."""
    check = getattr(settings, 'EMAIL2POST_CHECK', {})
    for lhs in check:
        value = str(make_header(decode_header(msg.get(lhs, ''))))
        if check[lhs] not in value:
            return False
    return True


def _is_attachment(part: Any) -> bool:
    content_type = part.get_content_type()
    if content_type == 'text/plain':
        return part.get_filename(None) is not None
    return bool(content_type.startswith(ATTACHMENT_PREFIXES))


def _save_attachment(part: Any) -> TemporaryUploadedFile:
    payload = part.get_payload(decode=True)
    os.umask(0)
    tmp = TemporaryUploadedFile(
        name=part.get_filename('attachment'),
        content_type=part.get_content_type(),
        size=len(payload),
        charset=None,
    )
    tmp.write(payload)
    tmp.seek(0)
    os.chmod(cast(Any, tmp.file).name, 0o644)
    return tmp


def _extract_parts(msg: Any) -> tuple[Any, list[TemporaryUploadedFile]]:
    """The body text and every attachment worth keeping."""
    if not msg.is_multipart():
        return msg.get_payload(decode=True), []

    content: Any = None
    files: list[TemporaryUploadedFile] = []
    for part in msg.walk():
        if _is_attachment(part):
            files.append(_save_attachment(part))
        elif part.get_content_type() == 'text/plain':
            content = part.get_payload(decode=True)
    return content, files


def _parse_subject(subject: str | None) -> dict[str, Any]:
    """Pull the title plus any @class, !draft and !friends-only markers."""
    args: dict[str, Any] = {}
    if not subject:
        return args

    title = str(make_header(decode_header(subject)))

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

    def share(self, msgfile: IO[Any] | Any) -> int:
        msg = email.message_from_file(msgfile)
        if not _sender_is_allowed(msg):
            return 77  # EX_NOPERM

        content, files = _extract_parts(msg)

        args: dict[str, Any] = _parse_subject(msg.get('Subject', None))
        if content is not None:
            args['content'] = content

        if files:
            args['files'] = MultiValueDict()
            args['files'].setlist('docs', files)

        selfposts.SelfpostsService(Service()).share(args)
        return 0  # EX_OK
