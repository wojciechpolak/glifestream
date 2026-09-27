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
from collections.abc import Callable, Iterable, Iterator
from functools import partial
from typing import Any
from urllib.parse import quote

from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.html import escape
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from glifestream.apis.base import BaseService, set_reblog
from glifestream.gauth import gls_oauth2
from glifestream.ingestion import Candidate, NormalizedEntry
from glifestream.stream import media
from glifestream.stream.models import Entry, Service
from glifestream.utils import httpclient, safe_markdown

WEB_URL = 'https://github.com'
AVATAR_URL = 'https://avatars.githubusercontent.com/%s'

# The kinds of activity a service can import, in the order Settings lists
# them. `Service.options[OPTIONS_KEY]` holds the chosen ones.
EVENT_CATEGORIES = ('repo', 'release', 'star', 'fork', 'pr', 'issue', 'push')
DEFAULT_EVENTS = ('repo', 'release')
OPTIONS_KEY = 'github_events'

# A release made by automation (a workflow, a release bot) is not the user's
# own event, so a user timeline reads releases from the user's repositories
# instead. One fetch looks at this many of the most recently pushed ones, and
# at those pushed since a day before the previous fetch: a release follows
# the push that triggered it.
MAX_RELEASE_REPOS = 10
RELEASES_PER_REPO = 5
RELEASE_LOOKBACK = datetime.timedelta(days=1)
# Release notes longer than this are cut at a line, with a link to the rest.
RELEASE_NOTES_LIMIT = 4000
# The newest commits of a push its entry lists.
MAX_PUSH_COMMITS = 10
# A response that means GitHub has nothing more to tell about an event: the
# commits were force-pushed away, the pull request is gone, the repository
# is empty.
NO_DETAILS_STATUSES = (404, 409, 410, 422)

# An event's entry has this guid prefix, then the event type and id.
EVENT_GUID_PREFIX = 'tag:github.com,2008:'
# The event types of each category but release, whose entries have the
# release's page as guid.
CATEGORY_EVENT_TYPES = {
    'repo': ('CreateEvent', 'PublicEvent'),
    'star': ('WatchEvent',),
    'fork': ('ForkEvent',),
    'pr': ('PullRequestEvent',),
    'issue': ('IssuesEvent',),
    'push': ('PushEvent',),
}

SIMPLE_EVENT_CATEGORIES = {
    'PublicEvent': 'repo',
    'WatchEvent': 'star',
    'ForkEvent': 'fork',
    'PushEvent': 'push',
}


def enabled_events(service: Service) -> tuple[str, ...]:
    """The event categories `service` imports."""
    chosen = (service.options or {}).get(OPTIONS_KEY)
    if not isinstance(chosen, list):
        return DEFAULT_EVENTS
    return tuple(c for c in EVENT_CATEGORIES if c in chosen)


def event_category(event: dict) -> str | None:
    """The category of a GitHub event, or None for one never imported."""
    kind = event.get('type')
    payload = event.get('payload') or {}
    action = payload.get('action')
    if kind == 'CreateEvent':
        # A new branch or tag is not worth an entry.
        return 'repo' if payload.get('ref_type') == 'repository' else None
    if kind == 'ReleaseEvent':
        return 'release' if action == 'published' else None
    if kind == 'PullRequestEvent':
        return 'pr' if action in ('opened', 'merged') else None
    if kind == 'IssuesEvent':
        return 'issue' if action == 'opened' else None
    return SIMPLE_EVENT_CATEGORIES.get(str(kind))


def category_entries(service: Service, categories: Iterable[str]) -> QuerySet[Entry]:
    """The entries of `service` imported for any of `categories`."""
    match = Q()
    for category in categories:
        if category == 'release':
            match |= Q(guid__startswith=WEB_URL + '/', guid__contains='/releases/')
        for kind in CATEGORY_EVENT_TYPES.get(category, ()):
            match |= Q(guid__startswith='%s%s/' % (EVENT_GUID_PREFIX, kind))
    if not match:
        return Entry.objects.none()
    return Entry.objects.filter(match, service=service)


def show_enabled_entries(service: Service, before: Iterable[str]) -> tuple[int, int]:
    """Hides the entries of the categories `service` no longer imports.

    The entries of the categories turned on since `before` are shown again.
    Returns how many entries were hidden and how many shown.
    """
    was, now = set(before), set(enabled_events(service))
    hidden = category_entries(service, was - now).filter(active=True)
    shown = category_entries(service, now - was).filter(active=False)
    return hidden.update(active=False), shown.update(active=True)


class GitHubService(BaseService):
    name = 'GitHub REST API'
    base_url = 'https://api.github.com'
    limit_sec = 120

    def __init__(
        self, service: Service, verbose: int = 0, force_overwrite: bool = False
    ) -> None:
        super().__init__(service, verbose, force_overwrite)
        self._oauth_client: gls_oauth2.OAuth2Client | None = None
        self._details: dict[str, Any] = {}

    def get_base_url(self) -> str:
        return self.base_url

    def get_authorize_url(self) -> str:
        return WEB_URL + '/login/oauth/authorize'

    def get_token_url(self) -> str:
        return WEB_URL + '/login/oauth/access_token'

    def get_oauth_scopes(self) -> list[str]:
        # No scope grants read access to public data, all a stream shows.
        return []

    def get_urls(self) -> list[str]:
        if not self.service.user_id:
            return []
        return ['%s/%s.atom' % (WEB_URL, quote(self.service.user_id))]

    def run(self) -> None:
        previous_check = self.service.last_checked
        categories = set(enabled_events(self.service))
        candidates: list[Candidate] = []

        if self.service.user_id:
            login = self.service.user_id
            events_path = '/users/%s/events/public?per_page=100' % quote(login)
            # A user timeline reads releases from the repositories instead.
            event_categories = categories - {'release'}
        else:
            login = self._get_json('/user')['login']
            events_path = '/users/%s/received_events?per_page=100' % quote(login)
            event_categories = categories

        if event_categories:
            events = self._get_json(events_path)
            candidates.extend(self._event_candidates(events, event_categories))
        if self.service.user_id and 'release' in categories:
            candidates.extend(self._repo_release_candidates(login, previous_check))

        self.service.last_checked = timezone.now()
        self.service.save()
        self.ingest(candidates)

    def _get_json(self, path: str) -> Any:
        url = self.base_url + path
        consumer = self._get_consumer()
        if consumer is not None:
            response = httpclient.read(url, consumer.get)
        else:
            response = httpclient.get(url)
        return httpclient.require_json(response)

    def _detail(self, path: str) -> Any:
        """More about an event, fetched once per run; None if GitHub has none.

        Only the entries being written ask, so a skipped one costs nothing.
        Other failures, such as the rate limit, stop the import: the entries
        not yet written are tried again on the next fetch.
        """
        if path not in self._details:
            try:
                self._details[path] = self._get_json(path)
            except httpclient.FetchError as exc:
                if exc.status_code not in NO_DETAILS_STATUSES:
                    raise
                self._details[path] = None
        return self._details[path]

    def _get_consumer(self) -> Any:
        """The OAuth session to send requests with, or None to go anonymous.

        A home timeline needs a token. A user timeline uses one when the
        service has it, for the higher rate limit.
        """
        if self.service.user_id and self.service.creds != 'oauth2':
            return None
        if self._oauth_client is None:
            self._oauth_client = gls_oauth2.OAuth2Client(service=self.service, api=self)
        consumer = getattr(self._oauth_client, 'consumer', None)
        if consumer is None and not self.service.user_id:
            raise httpclient.build_fetch_error(
                category='auth',
                detail='The GitHub home timeline needs an access token.',
                retryable=False,
                url=self.base_url,
            )
        return consumer

    def _event_candidates(
        self, events: Iterable[dict], categories: set[str]
    ) -> Iterator[Candidate]:
        for event in events:
            category = event_category(event)
            if category not in categories:
                continue
            if event.get('public') is False and self.service.public:
                continue
            if self.verbose:
                print('ID: %s %s' % (event['type'], event['id']))
            if category == 'release':
                release = event['payload']['release']
                if not release.get('draft'):
                    yield self._release_candidate(event['repo']['name'], release)
                continue
            guid = '%s%s/%s' % (EVENT_GUID_PREFIX, event['type'], event['id'])
            created = _parse_time(event['created_at'])
            yield Candidate(
                guid,
                created,
                partial(self._normalize_event, guid, category, created, event),
            )

    def _repo_release_candidates(
        self, login: str, previous_check: datetime.datetime | None
    ) -> Iterator[Candidate]:
        repos = self._get_json(
            '/users/%s/repos?type=owner&sort=pushed&per_page=30' % quote(login)
        )
        cutoff = None
        # A forced overwrite looks at every recent repository again.
        if previous_check and not self.force_overwrite:
            cutoff = previous_check - RELEASE_LOOKBACK
        checked = 0
        for repo in repos:
            if repo.get('fork') or (repo.get('private') and self.service.public):
                continue
            if checked == MAX_RELEASE_REPOS:
                break
            pushed = repo.get('pushed_at')
            if not pushed:
                continue
            if cutoff and _parse_time(pushed) < cutoff:
                # Sorted by the last push: the rest are older still.
                break
            checked += 1
            releases = self._get_json(
                '/repos/%s/releases?per_page=%d'
                % (quote(repo['full_name']), RELEASES_PER_REPO)
            )
            for release in releases:
                if release.get('draft') or not release.get('published_at'):
                    continue
                yield self._release_candidate(repo['full_name'], release)

    def _release_candidate(self, repo: str, release: dict) -> Candidate:
        # The same guid whichever way the release arrives.
        guid = release['html_url']
        published = _parse_time(release['published_at'])
        updated = release.get('updated_at')
        freshness = max(published, _parse_time(updated)) if updated else published
        return Candidate(
            guid,
            freshness,
            partial(self._normalize_release, guid, repo, published, release),
        )

    def _normalize_event(
        self, guid: str, category: str, created: datetime.datetime, event: dict
    ) -> NormalizedEntry:
        title, link, content = RENDERERS[category](
            event['repo']['name'], event, self._detail
        )
        actor = event['actor']
        e = NormalizedEntry(guid=guid)
        e.title = title[:255]
        e.link = link
        e.content = content
        e.date_published = created
        e.date_updated = created
        e.author_name = actor.get('display_login') or actor['login']
        e.author_uri = '%s/%s' % (WEB_URL, actor['login'])
        e.link_image = media.save_image(actor['avatar_url'], direct_image=False)
        set_reblog(e, False)
        return e

    def _normalize_release(
        self, guid: str, repo: str, published: datetime.datetime, release: dict
    ) -> NormalizedEntry:
        # The repository's owner, even when a bot published the release.
        owner = repo.split('/', 1)[0]
        e = NormalizedEntry(guid=guid)
        e.title = (
            _('Released %(repo)s %(release)s')
            % {'repo': _repo_label(repo, owner), 'release': _release_name(release)}
        )[:255]
        e.link = release['html_url']
        e.content = _render_release(repo, release)
        e.date_published = published
        e.date_updated = published
        e.author_name = owner
        e.author_uri = '%s/%s' % (WEB_URL, owner)
        e.link_image = media.save_image(AVATAR_URL % owner, direct_image=False)
        set_reblog(e, False)
        return e


def filter_title(entry: Entry) -> str:
    # Stored as plain text; the stream renders titles as HTML.
    return escape(entry.title)


def _parse_time(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))


def _repo_url(repo: str) -> str:
    return '%s/%s' % (WEB_URL, repo)


def _repo_label(repo: str, author: str) -> str:
    """How a title names `repo`: without the owner when the author owns it."""
    owner, _sep, name = repo.partition('/')
    return name if name and owner.lower() == author.lower() else repo


def _event_repo_label(repo: str, event: dict) -> str:
    return _repo_label(repo, event['actor']['login'])


def _link(url: str, text: str) -> str:
    return '<a href="%s">%s</a>' % (escape(url), escape(text))


def _release_name(release: dict) -> str:
    return release.get('name') or release.get('tag_name') or ''


def _render_release(repo: str, release: dict) -> str:
    name = _release_name(release)
    tag = release.get('tag_name') or ''
    # The sentence the title says, so the entry reads well without its title.
    content = '<p>%s' % (
        escape(_('Released %(repo)s %(release)s'))
        % {
            'repo': _link(_repo_url(repo), repo),
            'release': _link(release['html_url'], name),
        }
    )
    if tag and tag != name:
        content += ' (%s)' % escape(tag)
    content += '</p>'
    body = (release.get('body') or '').strip()
    if body:
        body, cut = safe_markdown.excerpt(body, RELEASE_NOTES_LIMIT)
        content += safe_markdown.render(body, _repo_url(repo) + '/')
        if cut:
            content += '<p>%s</p>' % _link(release['html_url'], _('Full release notes'))
    return content


Rendered = tuple[str, str, str]

# Fetches a GitHub API path for more about an event, or None if GitHub has none.
Fetch = Callable[[str], Any]


def _sentence(template: str, **parts: str) -> str:
    """A translated sentence with its parts, already HTML, put in."""
    return '<p>%s</p>' % (escape(template) % parts)


def _markdown_excerpt(repo: str, text: str | None) -> str:
    body = (text or '').strip()
    if not body:
        return ''
    body, _cut = safe_markdown.excerpt(body, RELEASE_NOTES_LIMIT)
    return safe_markdown.render(body, _repo_url(repo) + '/')


def _repo_summary(info: dict | None) -> str:
    """A repository's description, language and stars."""
    if not info:
        return ''
    content = ''
    if info.get('description'):
        content += '<p>%s</p>' % escape(info['description'])
    facts: list[str] = []
    if info.get('language'):
        facts.append(escape(info['language']))
    if info.get('stargazers_count'):
        facts.append('&#9733; %d' % info['stargazers_count'])
    if facts:
        content += '<p class="github-facts">%s</p>' % ' &middot; '.join(facts)
    return content


def _render_repo(repo: str, event: dict, fetch: Fetch) -> Rendered:
    url = _repo_url(repo)
    label = _event_repo_label(repo, event)
    if event['type'] == 'PublicEvent':
        template = _('Made %s public')
        info = fetch('/repos/%s' % quote(repo))
    else:
        template = _('Created repository %s')
        # The event carries the description the repository started with.
        info = {'description': event['payload'].get('description')}
    content = _sentence(template.replace('%s', '%(repo)s'), repo=_link(url, repo))
    return template % label, url, content + _repo_summary(info)


def _render_star(repo: str, event: dict, fetch: Fetch) -> Rendered:
    url = _repo_url(repo)
    template = _('Starred %s')
    content = _sentence(template.replace('%s', '%(repo)s'), repo=_link(url, repo))
    content += _repo_summary(fetch('/repos/%s' % quote(repo)))
    return template % _event_repo_label(repo, event), url, content


def _render_fork(repo: str, event: dict, fetch: Fetch) -> Rendered:
    forkee = event['payload'].get('forkee') or {}
    fork_name = forkee.get('full_name') or repo
    fork_url = forkee.get('html_url') or _repo_url(fork_name)
    template = _('Forked %s')
    content = _sentence(
        template.replace('%s', '%(repo)s'), repo=_link(_repo_url(repo), repo)
    )
    content += '<p>&rarr; %s</p>' % _link(fork_url, fork_name)
    content += _repo_summary({'description': forkee.get('description')})
    return template % _event_repo_label(repo, event), fork_url, content


def _render_pr(repo: str, event: dict, fetch: Fetch) -> Rendered:
    payload = event['payload']
    number = payload.get('number') or (payload.get('pull_request') or {}).get('number')
    # GitHub no longer sends the title of a pull request with its event.
    pull = fetch('/repos/%s/pulls/%s' % (quote(repo), number)) or {}
    url = pull.get('html_url') or '%s/pull/%s' % (_repo_url(repo), number)
    merged = payload.get('action') == 'merged'
    if merged:
        template = _('Merged pull request #%(number)s in %(repo)s')
    else:
        template = _('Opened pull request #%(number)s in %(repo)s')
    label = _event_repo_label(repo, event)
    title = template % {'number': number, 'repo': label}
    content = _sentence(
        template.replace('#%(number)s', '%(number)s'),
        number=_link(url, '#%s' % number),
        repo=_link(_repo_url(repo), repo),
    )
    if pull.get('title'):
        if merged:
            template = _('Merged pull request #%(number)s in %(repo)s: %(title)s')
        else:
            template = _('Opened pull request #%(number)s in %(repo)s: %(title)s')
        title = template % {'number': number, 'repo': label, 'title': pull['title']}
        content += '<p><strong>%s</strong></p>' % _link(url, pull['title'])
        content += _pull_facts(pull)
        content += _markdown_excerpt(repo, pull.get('body'))
    return title, url, content


def _pull_facts(pull: dict) -> str:
    """The branches of a pull request and the size of its change."""
    facts: list[str] = []
    head = (pull.get('head') or {}).get('ref')
    base = (pull.get('base') or {}).get('ref')
    if head and base:
        facts.append(
            '<code>%s</code> &rarr; <code>%s</code>' % (escape(head), escape(base))
        )
    if pull.get('additions') is not None and pull.get('deletions') is not None:
        facts.append('+%d &minus;%d' % (pull['additions'], pull['deletions']))
    if not facts:
        return ''
    return '<p class="github-facts">%s</p>' % ' &middot; '.join(facts)


def _render_issue(repo: str, event: dict, fetch: Fetch) -> Rendered:
    issue = event['payload'].get('issue') or {}
    number = issue.get('number')
    url = issue.get('html_url') or '%s/issues/%s' % (_repo_url(repo), number)
    label = _event_repo_label(repo, event)
    template = _('Opened issue #%(number)s in %(repo)s')
    title = template % {'number': number, 'repo': label}
    content = _sentence(
        template.replace('#%(number)s', '%(number)s'),
        number=_link(url, '#%s' % number),
        repo=_link(_repo_url(repo), repo),
    )
    if issue.get('title'):
        title = _('Opened issue #%(number)s in %(repo)s: %(title)s') % {
            'number': number,
            'repo': label,
            'title': issue['title'],
        }
        content += '<p><strong>%s</strong></p>' % _link(url, issue['title'])
        content += _markdown_excerpt(repo, issue.get('body'))
    return title, url, content


def _render_push(repo: str, event: dict, fetch: Fetch) -> Rendered:
    payload = event['payload']
    branch = (payload.get('ref') or '').removeprefix('refs/heads/')
    before = payload.get('before') or ''
    head = payload.get('head') or ''
    commits: list[dict] = []
    total = 0
    if head and before.strip('0'):
        url = '%s/compare/%s...%s' % (_repo_url(repo), before[:12], head[:12])
        compared = fetch(
            '/repos/%s/compare/%s...%s' % (quote(repo), before[:12], head[:12])
        )
        if compared:
            commits = compared.get('commits') or []
            total = compared.get('total_commits') or len(commits)
    elif head:
        # A new branch: nothing to compare it with, so its newest commit.
        url = '%s/commit/%s' % (_repo_url(repo), head)
        commit = fetch('/repos/%s/commits/%s' % (quote(repo), head))
        if commit:
            commits, total = [commit], 1
    else:
        url = _repo_url(repo)

    values = {'branch': branch, 'repo': _event_repo_label(repo, event)}
    links = {'branch': _link(url, branch), 'repo': _link(_repo_url(repo), repo)}
    if total:
        template = ngettext(
            'Pushed %(count)d commit to %(branch)s in %(repo)s',
            'Pushed %(count)d commits to %(branch)s in %(repo)s',
            total,
        )
        title = template % {'count': total, **values}
        content = _sentence(template.replace('%(count)d', str(total)), **links)
    else:
        template = _('Pushed to %(branch)s in %(repo)s')
        title = template % values
        content = _sentence(template, **links)

    shown = commits[-MAX_PUSH_COMMITS:]
    if shown:
        content += '<ul>%s</ul>' % ''.join(_commit_item(c) for c in shown)
    if total > len(shown):
        content += '<p>%s</p>' % _link(url, _('See all changes'))
    return title, url, content


def _commit_item(commit: dict) -> str:
    sha = commit.get('sha') or ''
    message = ((commit.get('commit') or {}).get('message') or '').strip()
    first_line = message.splitlines()[0] if message else ''
    return '<li><a href="%s"><code>%s</code></a> %s</li>' % (
        escape(commit.get('html_url') or ''),
        escape(sha[:7]),
        escape(first_line),
    )


RENDERERS: dict[str, Callable[[str, dict, Fetch], Rendered]] = {
    'repo': _render_repo,
    'star': _render_star,
    'fork': _render_fork,
    'pr': _render_pr,
    'issue': _render_issue,
    'push': _render_push,
}
