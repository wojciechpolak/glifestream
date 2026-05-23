"""
#  gLifestream Copyright (C) 2023, 2024 Wojciech Polak
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

import sys
import traceback
import datetime
import re
from typing import cast
from django.utils import timezone
from django.utils.html import escape, strip_tags
from django.utils.translation import gettext as _

from glifestream.apis.base import BaseService
from glifestream.filters import expand, truncate
from glifestream.gauth import gls_oauth2
from glifestream.utils import httpclient
from glifestream.utils.html import strip_entities
from glifestream.utils.time import mtime
from glifestream.stream.models import Entry, Service
from glifestream.stream import media

QUOTE_INLINE_RE = re.compile(r'^\s*<p class="quote-inline">.*?</p>\s*', re.S)
DISPLAYABLE_QUOTE_STATES = {
    'accepted',
    'blocked_account',
    'blocked_domain',
    'muted_account',
}


class MastodonService(BaseService):
    name = 'Mastodon API v1.0'
    base_url = 'https://mastodon.social'
    limit_sec = 120

    def __init__(
        self, service: Service, verbose: int = 0, force_overwrite: bool = False
    ) -> None:
        super().__init__(service, verbose, force_overwrite)
        self._status_cache: dict[str, dict | None] = {}
        self._oauth_client: gls_oauth2.OAuth2Client | None = None

    def get_base_url(self) -> str:
        return self.service.url or self.base_url

    def get_authorize_url(self) -> str:
        return self.get_base_url() + '/oauth/authorize'

    def get_token_url(self) -> str:
        return self.get_base_url() + '/oauth/token'

    def get_urls(self) -> list[str]:
        if not self.service.user_id:
            return ['/api/v1/timelines/home?limit=40']
        if not self.service.last_checked:
            return ['/api/v1/accounts/%s/statuses?limit=40' % self.service.user_id]
        return ['/api/v1/accounts/%s/statuses' % self.service.user_id]

    def run(self) -> None:
        for url in self.get_urls():
            try:
                if not self.service.user_id:
                    self.fetch_oauth2(self.get_base_url() + url)
                else:
                    self.fetch(self.get_base_url() + url)
            except Exception as e:
                if self.verbose:
                    print(
                        '%s (%d) Exception: %s' % (self.service.api, self.service.pk, e)
                    )
                    traceback.print_exc(file=sys.stdout)

    def fetch(self, url) -> None:
        try:
            r = httpclient.get(url)
            self.process(r.json())
        except Exception as e:
            if self.verbose:
                print('%s (%d) Exception: %s' % (self.service.api, self.service.pk, e))
                traceback.print_exc(file=sys.stdout)

    def fetch_oauth2(self, url) -> None:
        try:
            oauth = self._get_oauth_client()
            r = oauth.consumer.get(url)
            if r.status_code == 200:
                self.json = r.json()
                self.service.last_checked = timezone.now()
                self.service.save()
                self.process(self.json)
            elif self.verbose:
                print(
                    '%s (%d) HTTP: %s' % (self.service.api, self.service.pk, r.reason)
                )
        except Exception as e:
            if self.verbose:
                print('%s (%d) Exception: %s' % (self.service.api, self.service.pk, e))
                traceback.print_exc(file=sys.stdout)

    def process(self, entries) -> None:
        for ent in entries:
            reblog = False
            entry = ent
            if ent['reblog']:
                reblog = True
                entry = ent['reblog']
            if reblog and self.service.skip_reblogs:
                if self.verbose:
                    print('Skipping reblogged ID: %s' % entry['url'])
                continue

            guid = entry['url']
            if self.verbose:
                print('ID: %s' % guid)

            t = datetime.datetime.fromisoformat(
                ent['created_at'].replace('Z', '+00:00')
            )

            try:
                e = Entry.objects.get(service=self.service, guid=guid)
                if (
                    not self.force_overwrite
                    and e.date_updated
                    and mtime(t.timetuple()) <= e.date_updated
                ):
                    continue
                if e.protected:
                    continue
            except Entry.DoesNotExist:
                e = Entry(service=self.service, guid=guid)

            e.guid = guid
            e.title = truncate.smart(
                strip_entities(strip_tags(entry['content'])), max_length=40
            )
            e.title = e.title.replace('#', '').replace('@', '')

            e.link = entry['url']
            image_url = entry['account']['avatar_static']
            e.link_image = media.save_image(image_url, direct_image=False)

            e.date_published = t
            e.date_updated = t
            e.author_name = entry['account']['display_name']

            e.content = self._render_entry_content(entry)
            e.reblog = False
            e.reblog_by = ''
            e.reblog_uri = ''
            if reblog:
                e.reblog = True
                e.reblog_by = ent['account']['display_name']
                e.reblog_uri = ent['uri']

            try:
                e.save()
                media.extract_and_register(e)
            except Exception:
                pass

    def _get_oauth_client(self) -> gls_oauth2.OAuth2Client:
        if self._oauth_client is None:
            self._oauth_client = gls_oauth2.OAuth2Client(service=self.service, api=self)
        return self._oauth_client

    def _render_entry_content(self, entry: dict) -> str:
        reply_context = self._render_reply_context(entry)
        quote_card = self._render_quote_card(entry.get('quote'))
        body = _render_status_body(entry['content'], strip_quote_inline=bool(quote_card))
        body = expand.run_all(expand.shorturls(body))
        body += _render_card(entry.get('card'), self.service.public)
        body += quote_card
        body += _render_media_attachments(entry, self.service.public)
        return reply_context + body

    def _render_reply_context(self, entry: dict) -> str:
        parent_id = entry.get('in_reply_to_id')
        if not parent_id:
            return ''

        parent_status = self._fetch_status(cast(str, parent_id))
        if parent_status:
            return _render_status_reference(parent_status, label=_('Replying to'))
        return _render_unavailable_reference(
            _status_url_from_id(self.get_base_url(), cast(str, parent_id)),
            _('Replying to'),
            _('Replied-to post unavailable.'),
        )

    def _render_quote_card(self, quote: dict | None) -> str:
        if not quote:
            return ''

        quoted_status = quote.get('quoted_status')
        if isinstance(quoted_status, dict):
            return _render_status_reference(quoted_status, label=_('Quoted post'))

        quote_state = quote.get('state')
        quoted_status_id = quote.get('quoted_status_id')
        if quote_state not in DISPLAYABLE_QUOTE_STATES or not quoted_status_id:
            return _render_quote_placeholder(quote, self.get_base_url())

        hydrated_status = self._fetch_status(cast(str, quoted_status_id))
        if hydrated_status:
            return _render_status_reference(hydrated_status, label=_('Quoted post'))
        return _render_quote_placeholder(quote, self.get_base_url())

    def _fetch_status(self, status_id: str) -> dict | None:
        if status_id not in self._status_cache:
            url = self.get_base_url() + '/api/v1/statuses/%s' % status_id
            try:
                if not self.service.user_id:
                    response = self._get_oauth_client().consumer.get(url)
                else:
                    response = httpclient.get(url)
                if response.status_code == 200:
                    self._status_cache[status_id] = cast(dict, response.json())
                else:
                    self._status_cache[status_id] = None
            except Exception:
                self._status_cache[status_id] = None
        return self._status_cache[status_id]


def filter_content(entry: Entry) -> str:
    if entry.reblog:
        return _('%s reblogged') % entry.reblog_by + '\n\n' + entry.content
    return entry.content


def _render_status_body(content: str, *, strip_quote_inline: bool) -> str:
    if strip_quote_inline:
        content = QUOTE_INLINE_RE.sub('', content, count=1)
    return content


def _render_card(card: dict | None, is_public: bool) -> str:
    if not card:
        return ''

    url = card.get('url')
    title = card.get('title') or url
    description = card.get('description') or ''
    if not isinstance(url, str) or not url:
        return ''

    card_markup = (
        ' <blockquote class="mastodon-card mastodon-preview">'
        '<p><a href="%s" rel="nofollow">%s</a></p>'
        % (escape(url), escape(cast(str, title)))
    )
    if description:
        card_markup += '<p>%s</p>' % escape(cast(str, description))

    image = card.get('image')
    if isinstance(image, str) and image:
        image_url = media.save_image(image) if is_public else image
        card_markup += (
            '<p class="thumbnails"><a href="%s" rel="nofollow">'
            '<img src="%s" alt="%s" /></a></p>'
            % (escape(url), escape(image_url), escape(cast(str, title)))
        )
    card_markup += '</blockquote>'
    return card_markup


def _render_status_reference(status: dict, *, label: str) -> str:
    account = cast(dict, status.get('account') or {})
    author_name = cast(str, account.get('display_name') or account.get('acct') or '')
    author_link = cast(str, account.get('url') or status.get('url') or '#')
    body = cast(str, status.get('content') or '')
    if not body:
        text = status.get('text')
        if isinstance(text, str) and text:
            body = '<p>%s</p>' % escape(text)
        else:
            body = '<p>%s</p>' % escape(_('No text content.'))

    return (
        ' <blockquote class="mastodon-card mastodon-reference">'
        '<p>%s <a href="%s" rel="nofollow">%s</a></p>%s</blockquote>'
        % (escape(label), escape(author_link), escape(author_name or author_link), body)
    )


def _render_quote_placeholder(quote: dict, base_url: str) -> str:
    quote_id = quote.get('quoted_status_id')
    message = _('Quoted post unavailable.')
    if quote.get('state') == 'pending':
        message = _('Quoted post pending approval.')

    if isinstance(quote_id, str) and quote_id:
        return _render_unavailable_reference(
            _status_url_from_id(base_url, quote_id),
            _('Quoted post'),
            message,
        )
    return (
        ' <blockquote class="mastodon-card mastodon-reference unavailable">'
        '<p>%s</p><p>%s</p></blockquote>'
        % (escape(_('Quoted post')), escape(message))
    )


def _render_unavailable_reference(url: str, label: str, message: str) -> str:
    return (
        ' <blockquote class="mastodon-card mastodon-reference unavailable">'
        '<p>%s</p><p><a href="%s" rel="nofollow">%s</a></p></blockquote>'
        % (escape(label), escape(url), escape(message))
    )


def _status_url_from_id(base_url: str, status_id: str) -> str:
    return '%s/web/statuses/%s' % (base_url.rstrip('/'), status_id)


def _render_media_attachments(entry: dict, is_public: bool) -> str:
    attachments = cast(list[dict], entry.get('media_attachments') or [])
    if not attachments:
        return ''

    content = ' <p class="thumbnails">'
    for attachment in attachments:
        if attachment.get('type') != 'image':
            continue
        image_url = cast(str, attachment['preview_url'])
        large_url = cast(str, attachment['url'])
        link = cast(str, attachment.get('remote_url') or attachment['url'])
        if is_public:
            image_url = media.save_image(image_url)
        if 'meta' in attachment and 'small' in attachment['meta']:
            sizes = attachment['meta']['small']
            iwh = ' width="%d" height="%d"' % (sizes['width'], sizes['height'])
        else:
            iwh = ''
        content += (
            '<a href="%s" rel="nofollow" data-imgurl="%s"><img src="%s"%s alt="thumbnail" /></a> '
            % (link, large_url, image_url, iwh)
        )
    content += '</p>'
    return content
