"""The GitHub provider: which activity becomes entries, and how.

The GitHub REST API is faked at `httpclient.get` (anonymous requests) and
`httpclient.read` (requests with a token), answering by path.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from glifestream.apis import github
from glifestream.apis.github import GitHubService
from glifestream.gauth.models import OAuthClient
from glifestream.stream.models import Entry, Service
from glifestream.utils import httpclient

API = 'https://api.github.com'
EVENTS = '/users/me/events/public?per_page=100'
REPOS = '/users/me/repos?type=owner&sort=pushed&per_page=30'


def releases_path(repo: str) -> str:
    return '/repos/%s/releases?per_page=5' % repo


def event(
    kind: str,
    event_id: int,
    payload: dict[str, Any],
    *,
    repo: str = 'me/app',
    actor: str = 'me',
    public: bool = True,
    created: str = '2026-09-20T10:00:00Z',
) -> dict[str, Any]:
    return {
        'id': str(event_id),
        'type': kind,
        'actor': {
            'login': actor,
            'display_login': actor,
            'avatar_url': 'https://avatars.githubusercontent.com/u/%s?' % actor,
        },
        'repo': {'name': repo, 'url': API + '/repos/' + repo},
        'payload': payload,
        'public': public,
        'created_at': created,
    }


def release(
    tag: str,
    *,
    repo: str = 'me/app',
    draft: bool = False,
    published: str | None = '2026-09-21T10:00:00Z',
    body: str = '',
) -> dict[str, Any]:
    return {
        'html_url': 'https://github.com/%s/releases/tag/%s' % (repo, tag),
        'tag_name': tag,
        'name': tag,
        'draft': draft,
        'published_at': published,
        'updated_at': published,
        'body': body,
        'author': {'login': 'github-actions[bot]'},
    }


def repo(
    name: str,
    *,
    pushed: str | None = '2026-09-21T09:00:00Z',
    fork: bool = False,
    private: bool = False,
) -> dict[str, Any]:
    return {
        'full_name': 'me/' + name,
        'fork': fork,
        'private': private,
        'pushed_at': pushed,
    }


PUSH = event(
    'PushEvent',
    1,
    {'ref': 'refs/heads/main', 'before': 'a' * 40, 'head': 'b' * 40},
)
NEW_REPO = event(
    'CreateEvent',
    2,
    {'ref': None, 'ref_type': 'repository', 'description': 'An <app>'},
)
NEW_BRANCH = event('CreateEvent', 3, {'ref': 'topic', 'ref_type': 'branch'})
STAR = event('WatchEvent', 4, {'action': 'started'}, repo='other/lib')
RELEASE_EVENT = event(
    'ReleaseEvent', 5, {'action': 'published', 'release': release('v1.0.0')}
)

# Where the push above finds its commits.
COMPARE = '/repos/me/app/compare/%s...%s' % ('a' * 12, 'b' * 12)


class FakeGitHub:
    """Answers GitHub API requests by path, 404 for the rest, and records them."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.requested: list[str] = []

    def get(self, url: str, *args: Any, **kwargs: Any) -> MagicMock:
        path = url.removeprefix(API)
        self.requested.append(path)
        if path not in self.routes:
            raise httpclient.build_fetch_error(
                category='remote_4xx', detail='Not Found', status_code=404, url=url
            )
        response = MagicMock()
        response.json.return_value = self.routes[path]
        return response

    def read(self, url: str, request_func: Any, **kwargs: Any) -> MagicMock:
        return self.get(url)


def run(service: Service, routes: dict[str, Any]) -> tuple[FakeGitHub, MagicMock]:
    fake = FakeGitHub(routes)
    with (
        patch('glifestream.apis.github.httpclient.get', fake.get),
        patch('glifestream.apis.github.httpclient.read', fake.read),
        patch(
            'glifestream.apis.github.media.save_image', return_value='avatar.png'
        ) as save_image,
    ):
        GitHubService(service).run()
    return fake, save_image


def guids(service: Service) -> set[str]:
    return set(Entry.objects.filter(service=service).values_list('guid', flat=True))


@pytest.fixture
def user_service(db) -> Service:
    return Service.objects.create(
        api='github', name='GitHub', user_id='me', public=True
    )


@pytest.fixture
def home_service(db) -> Service:
    service = Service.objects.create(
        api='github', name='GitHub home', creds='oauth2', public=True
    )
    OAuthClient.objects.create(service=service, token='gho_token', phase=3)
    return service


@pytest.mark.django_db
def test_user_timeline_imports_new_repositories_and_releases_by_default(
    user_service,
):
    routes = {
        EVENTS: [PUSH, NEW_REPO, NEW_BRANCH, STAR, RELEASE_EVENT],
        REPOS: [repo('app')],
        releases_path('me/app'): [release('v1.0.0'), release('v2.0.0')],
    }

    fake, save_image = run(user_service, routes)

    assert guids(user_service) == {
        'tag:github.com,2008:CreateEvent/2',
        'https://github.com/me/app/releases/tag/v1.0.0',
        'https://github.com/me/app/releases/tag/v2.0.0',
    }
    assert fake.requested == [EVENTS, REPOS, releases_path('me/app')]
    # Only the entries kept fetch an avatar.
    assert save_image.call_count == 3


@pytest.mark.django_db
def test_a_release_by_automation_belongs_to_the_repository_owner(user_service):
    routes = {
        EVENTS: [],
        REPOS: [repo('app')],
        releases_path('me/app'): [release('v2.0.0', body='Fixes <b>bugs</b>.')],
    }

    run(user_service, routes)

    e = Entry.objects.get(service=user_service)
    assert e.title == 'Released app v2.0.0'
    assert e.link == 'https://github.com/me/app/releases/tag/v2.0.0'
    assert e.author_name == 'me'
    assert e.author_uri == 'https://github.com/me'
    # The content says it too, for a service that shows no titles.
    assert e.content.startswith(
        '<p>Released <a href="https://github.com/me/app">me/app</a> '
        '<a href="https://github.com/me/app/releases/tag/v2.0.0">v2.0.0</a></p>'
    )
    assert 'Fixes &lt;b&gt;bugs&lt;/b&gt;.' in e.content
    assert '<b>' not in e.content


def test_release_notes_render_as_markdown():
    notes = '### Features\n\n* **cli:** add `--dry-run` ([abc1234](../commit/abc1234))'
    content = github._render_release('me/app', release('v1.0.0', body=notes))

    assert '<p><strong>Features</strong></p>' in content
    assert '<li><strong>cli:</strong> add <code>--dry-run</code>' in content
    assert 'href="https://github.com/me/commit/abc1234"' in content
    assert '###' not in content


def test_very_long_release_notes_link_to_the_rest():
    notes = '\n'.join('* change %d' % i for i in range(1000))
    content = github._render_release('me/app', release('v1.0.0', body=notes))

    assert '<li>change 0</li>' in content
    assert '<li>change 999</li>' not in content
    assert content.endswith(
        '<p><a href="https://github.com/me/app/releases/tag/v1.0.0">'
        'Full release notes</a></p>'
    )
    assert '...' not in content


@pytest.mark.django_db
def test_chosen_categories_replace_the_defaults(user_service):
    user_service.options = {github.OPTIONS_KEY: ['push']}
    user_service.save()

    fake, _ = run(user_service, {EVENTS: [PUSH, NEW_REPO, STAR]})

    assert guids(user_service) == {'tag:github.com,2008:PushEvent/1'}
    # Releases are off, so the repositories are not read; the push asks
    # for its commits.
    assert fake.requested == [EVENTS, COMPARE]


@pytest.mark.django_db
def test_releases_alone_skip_the_event_list(user_service):
    user_service.options = {github.OPTIONS_KEY: ['release']}
    user_service.save()

    fake, _ = run(
        user_service,
        {REPOS: [repo('app')], releases_path('me/app'): [release('v1.0.0')]},
    )

    assert fake.requested == [REPOS, releases_path('me/app')]
    assert guids(user_service) == {'https://github.com/me/app/releases/tag/v1.0.0'}


@pytest.mark.django_db
def test_nothing_chosen_imports_nothing(user_service):
    user_service.options = {github.OPTIONS_KEY: []}
    user_service.save()

    fake, _ = run(user_service, {})

    assert fake.requested == []
    user_service.refresh_from_db()
    assert user_service.last_checked is not None


@pytest.mark.django_db
def test_release_scan_skips_forks_drafts_and_stale_repositories(user_service):
    user_service.last_checked = datetime.datetime(
        2026, 9, 21, 12, 0, tzinfo=datetime.timezone.utc
    )
    user_service.save()
    routes = {
        EVENTS: [],
        REPOS: [
            repo('fork', fork=True),
            repo('empty', pushed=None),
            repo('app', pushed='2026-09-21T09:00:00Z'),
            # Pushed more than a day before the previous check.
            repo('old', pushed='2026-09-19T09:00:00Z'),
            repo('older', pushed='2026-09-01T09:00:00Z'),
        ],
        releases_path('me/app'): [
            release('v3.0.0', draft=True, published=None),
            release('v2.0.0'),
        ],
    }

    fake, _ = run(user_service, routes)

    assert fake.requested == [EVENTS, REPOS, releases_path('me/app')]
    assert guids(user_service) == {'https://github.com/me/app/releases/tag/v2.0.0'}


@pytest.mark.django_db
def test_forced_overwrite_scans_repositories_pushed_long_ago(user_service):
    user_service.last_checked = datetime.datetime(
        2026, 9, 21, 12, 0, tzinfo=datetime.timezone.utc
    )
    user_service.save()
    routes = {
        EVENTS: [],
        REPOS: [repo('old', pushed='2026-09-01T09:00:00Z')],
        releases_path('me/old'): [release('v1.0.0', repo='me/old')],
    }
    fake = FakeGitHub(routes)

    with (
        patch('glifestream.apis.github.httpclient.get', fake.get),
        patch('glifestream.apis.github.media.save_image', return_value='a.png'),
    ):
        GitHubService(user_service, force_overwrite=True).run()

    assert releases_path('me/old') in fake.requested
    assert guids(user_service) == {'https://github.com/me/old/releases/tag/v1.0.0'}


@pytest.mark.django_db
def test_release_scan_checks_a_bounded_number_of_repositories(
    user_service: Service,
) -> None:
    names = ['r%d' % i for i in range(github.MAX_RELEASE_REPOS + 5)]
    routes: dict[str, Any] = {EVENTS: [], REPOS: [repo(name) for name in names]}
    routes.update({releases_path('me/' + name): [] for name in names})

    fake, _ = run(user_service, routes)

    assert len(fake.requested) == 2 + github.MAX_RELEASE_REPOS


@pytest.mark.django_db
def test_private_repositories_stay_off_a_public_stream(user_service):
    routes = {
        EVENTS: [],
        REPOS: [repo('secret', private=True)],
        releases_path('me/secret'): [release('v1.0.0', repo='me/secret')],
    }

    fake, _ = run(user_service, routes)

    assert releases_path('me/secret') not in fake.requested
    assert not guids(user_service)


@pytest.mark.django_db
def test_a_second_fetch_of_the_same_activity_changes_nothing(user_service):
    routes = {
        EVENTS: [NEW_REPO],
        REPOS: [repo('app')],
        releases_path('me/app'): [release('v1.0.0')],
    }
    run(user_service, routes)

    service = GitHubService(user_service)
    fake = FakeGitHub(routes)
    with (
        patch('glifestream.apis.github.httpclient.get', fake.get),
        patch('glifestream.apis.github.media.save_image') as save_image,
    ):
        service.run()

    assert service.last_result.created == 0
    assert service.last_result.updated == 0
    assert not save_image.called


@pytest.mark.django_db
def test_home_timeline_reads_the_received_events_with_the_token(home_service):
    routes = {
        '/user': {'login': 'me'},
        '/users/me/received_events?per_page=100': [
            STAR,
            RELEASE_EVENT,
            event('CreateEvent', 6, {'ref_type': 'repository'}, public=False),
        ],
    }
    home_service.options = {github.OPTIONS_KEY: ['repo', 'release', 'star']}
    home_service.save()

    fake = FakeGitHub(routes)
    read = MagicMock(side_effect=fake.read)
    with (
        patch('glifestream.apis.github.httpclient.get') as get,
        patch('glifestream.apis.github.httpclient.read', read),
        patch('glifestream.apis.github.media.save_image', return_value='a.png'),
    ):
        GitHubService(home_service).run()

    assert not get.called
    assert fake.requested == [
        '/user',
        '/users/me/received_events?per_page=100',
        # What the starred repository is about.
        '/repos/other/lib',
    ]
    # The private repository's event stays off the public stream.
    assert guids(home_service) == {
        'tag:github.com,2008:WatchEvent/4',
        'https://github.com/me/app/releases/tag/v1.0.0',
    }
    star = Entry.objects.get(guid='tag:github.com,2008:WatchEvent/4')
    assert star.title == 'Starred other/lib'
    assert star.author_name == 'me'


@pytest.mark.django_db
def test_a_private_stream_keeps_private_activity(home_service):
    home_service.public = False
    home_service.save()
    routes = {
        '/user': {'login': 'me'},
        '/users/me/received_events?per_page=100': [
            event('CreateEvent', 6, {'ref_type': 'repository'}, public=False),
        ],
    }

    run(home_service, routes)

    assert guids(home_service) == {'tag:github.com,2008:CreateEvent/6'}


@pytest.mark.django_db
def test_home_timeline_without_a_token_is_an_auth_failure(db):
    service = Service.objects.create(api='github', name='GitHub home')

    with (
        patch('glifestream.apis.github.httpclient.get') as get,
        pytest.raises(httpclient.FetchError) as raised,
    ):
        GitHubService(service).run()

    assert raised.value.category == 'auth'
    assert not raised.value.retryable
    assert not get.called


@pytest.mark.django_db
def test_a_user_timeline_uses_a_token_when_it_has_one(user_service):
    user_service.creds = 'oauth2'
    user_service.save()
    OAuthClient.objects.create(service=user_service, token='github_pat_' + 'x' * 82)
    user_service.options = {github.OPTIONS_KEY: ['push']}
    user_service.save()

    fake = FakeGitHub({EVENTS: [PUSH]})
    with (
        patch('glifestream.apis.github.httpclient.get') as get,
        patch('glifestream.apis.github.httpclient.read', side_effect=fake.read),
        patch('glifestream.apis.github.media.save_image', return_value='a.png'),
    ):
        GitHubService(user_service).run()

    assert not get.called
    assert fake.requested == [EVENTS, COMPARE]


@pytest.mark.parametrize(
    'raw, category',
    [
        (NEW_REPO, 'repo'),
        (event('PublicEvent', 7, {}), 'repo'),
        (NEW_BRANCH, None),
        (event('CreateEvent', 8, {'ref': 'v1', 'ref_type': 'tag'}), None),
        (RELEASE_EVENT, 'release'),
        (event('ReleaseEvent', 9, {'action': 'edited'}), None),
        (STAR, 'star'),
        (event('ForkEvent', 10, {'forkee': {}}), 'fork'),
        (event('PullRequestEvent', 11, {'action': 'opened'}), 'pr'),
        (event('PullRequestEvent', 12, {'action': 'merged'}), 'pr'),
        (event('PullRequestEvent', 13, {'action': 'labeled'}), None),
        (event('IssuesEvent', 14, {'action': 'opened'}), 'issue'),
        (event('IssuesEvent', 15, {'action': 'closed'}), None),
        (PUSH, 'push'),
        (event('DeleteEvent', 16, {}), None),
        (event('IssueCommentEvent', 17, {'action': 'created'}), None),
    ],
)
def test_event_category(raw, category):
    assert github.event_category(raw) == category


def test_enabled_events_default_and_order():
    service = Service(api='github')
    assert github.enabled_events(service) == ('repo', 'release')

    service.options = {github.OPTIONS_KEY: ['push', 'bogus', 'repo']}
    assert github.enabled_events(service) == ('repo', 'push')


def nothing(path: str) -> None:
    """A fetch for when GitHub has no more to tell."""
    return None


def answers(routes: dict[str, Any]) -> Any:
    """A fetch that answers from `routes`, like GitHub with 404 for the rest."""
    return routes.get


PR_MERGED = event(
    'PullRequestEvent',
    12,
    {'action': 'merged', 'number': 31, 'pull_request': {'number': 31}},
)


def test_pull_request_without_details_still_says_what_happened():
    title, link, content = github.RENDERERS['pr']('me/app', PR_MERGED, nothing)

    assert title == 'Merged pull request #31 in app'
    assert link == 'https://github.com/me/app/pull/31'
    assert content == (
        '<p>Merged pull request <a href="https://github.com/me/app/pull/31">#31</a>'
        ' in <a href="https://github.com/me/app">me/app</a></p>'
    )


def test_pull_request_shows_its_title_branches_and_description():
    pull = {
        'title': 'Code <quality>',
        'html_url': 'https://github.com/me/app/pull/31',
        'head': {'ref': 'code-quality'},
        'base': {'ref': 'main'},
        'additions': 120,
        'deletions': 4,
        'body': 'Fixes **all** the <b>things</b>.',
    }
    fetch = answers({'/repos/me/app/pulls/31': pull})

    title, _, content = github.RENDERERS['pr']('me/app', PR_MERGED, fetch)

    assert title == 'Merged pull request #31 in app: Code <quality>'
    assert (
        '<strong><a href="https://github.com/me/app/pull/31">Code &lt;quality&gt;'
        in content
    )
    assert '<code>code-quality</code> &rarr; <code>main</code>' in content
    assert '+120 &minus;4' in content
    assert '<strong>all</strong>' in content
    assert '<b>' not in content


def test_opened_issue_shows_its_title_and_description():
    raw = event(
        'IssuesEvent',
        14,
        {
            'action': 'opened',
            'issue': {
                'number': 7,
                'title': 'Crash on <start>',
                'html_url': 'https://github.com/me/app/issues/7',
                'body': 'Steps:\n\n1. run `app`',
            },
        },
    )

    title, link, content = github.RENDERERS['issue']('me/app', raw, nothing)

    assert title == 'Opened issue #7 in app: Crash on <start>'
    assert link == 'https://github.com/me/app/issues/7'
    assert content.startswith(
        '<p>Opened issue <a href="https://github.com/me/app/issues/7">#7</a>'
    )
    assert 'Crash on &lt;start&gt;' in content
    assert '<li>run <code>app</code></li>' in content


def commit(n: int, message: str = '') -> dict[str, Any]:
    sha = '%040x' % n
    return {
        'sha': sha,
        'html_url': 'https://github.com/me/app/commit/' + sha,
        'commit': {'message': message or 'Change %d\n\nMore about it.' % n},
    }


def test_push_lists_its_newest_commits():
    commits = [commit(n) for n in range(12)]
    fetch = answers({COMPARE: {'commits': commits, 'total_commits': 12}})

    title, link, content = github.RENDERERS['push']('me/app', PUSH, fetch)

    compare_url = 'https://github.com/me/app/compare/%s...%s' % ('a' * 12, 'b' * 12)
    assert title == 'Pushed 12 commits to main in app'
    assert link == compare_url
    assert content.startswith(
        '<p>Pushed 12 commits to <a href="%s">main</a> in ' % compare_url
    )
    assert content.count('<li>') == github.MAX_PUSH_COMMITS
    assert 'Change 0' not in content and 'Change 11' in content
    assert 'More about it' not in content
    assert '<code>%s</code>' % commit(11)['sha'][:7] in content
    assert content.endswith('<p><a href="%s">See all changes</a></p>' % compare_url)


def test_push_of_one_commit_escapes_its_message():
    fetch = answers(
        {COMPARE: {'commits': [commit(1, 'Fix <b>bold</b>')], 'total_commits': 1}}
    )

    title, _, content = github.RENDERERS['push']('me/app', PUSH, fetch)

    assert title == 'Pushed 1 commit to main in app'
    assert 'Fix &lt;b&gt;bold&lt;/b&gt;</li>' in content
    assert 'See all changes' not in content


def test_push_without_details_still_says_what_happened():
    title, link, content = github.RENDERERS['push']('me/app', PUSH, nothing)

    compare_url = 'https://github.com/me/app/compare/%s...%s' % ('a' * 12, 'b' * 12)
    assert title == 'Pushed to main in app'
    assert link == compare_url
    assert content == (
        '<p>Pushed to <a href="%s">main</a> in '
        '<a href="https://github.com/me/app">me/app</a></p>' % compare_url
    )


def test_push_of_a_new_branch_shows_its_head():
    raw = event(
        'PushEvent', 1, {'ref': 'refs/heads/new', 'before': '0' * 40, 'head': 'c' * 40}
    )
    fetch = answers({'/repos/me/app/commits/' + 'c' * 40: commit(3)})

    title, link, content = github.RENDERERS['push']('me/app', raw, fetch)

    assert title == 'Pushed 1 commit to new in app'
    assert link == 'https://github.com/me/app/commit/' + 'c' * 40
    assert 'Change 3' in content


def test_fork_links_to_the_new_repository():
    raw = event(
        'ForkEvent',
        10,
        {
            'forkee': {
                'full_name': 'me/lib',
                'html_url': 'https://github.com/me/lib',
                'description': 'A library',
            }
        },
        repo='other/lib',
    )

    title, link, content = github.RENDERERS['fork']('other/lib', raw, nothing)

    assert title == 'Forked other/lib'
    assert link == 'https://github.com/me/lib'
    assert content.startswith(
        '<p>Forked <a href="https://github.com/other/lib">other/lib</a></p>'
    )
    assert '&rarr; <a href="https://github.com/me/lib">me/lib</a>' in content
    assert '<p>A library</p>' in content


def test_new_repository_shows_its_escaped_description():
    title, link, content = github.RENDERERS['repo']('me/app', NEW_REPO, nothing)

    assert title == 'Created repository app'
    assert link == 'https://github.com/me/app'
    assert content == (
        '<p>Created repository <a href="https://github.com/me/app">me/app</a></p>'
        '<p>An &lt;app&gt;</p>'
    )


def test_star_describes_the_repository():
    info = {'description': 'Handy <lib>', 'language': 'Rust', 'stargazers_count': 42}
    fetch = answers({'/repos/other/lib': info})

    title, _, content = github.RENDERERS['star']('other/lib', STAR, fetch)

    assert title == 'Starred other/lib'
    assert '<p>Handy &lt;lib&gt;</p>' in content
    assert '<p class="github-facts">Rust &middot; &#9733; 42</p>' in content


def test_star_without_details_still_says_what_happened():
    _, _, content = github.RENDERERS['star']('other/lib', STAR, nothing)

    assert content == (
        '<p>Starred <a href="https://github.com/other/lib">other/lib</a></p>'
    )


def test_titles_name_someone_elses_repository_in_full():
    raw = event('PushEvent', 1, PUSH['payload'], repo='Other/lib', actor='me')
    title = github.RENDERERS['push']('Other/lib', raw, nothing)[0]
    assert title == 'Pushed to main in Other/lib'

    # The owner's own repository, whatever the case of the login.
    raw = event('PushEvent', 1, PUSH['payload'], repo='Me/app', actor='me')
    assert (
        github.RENDERERS['push']('Me/app', raw, nothing)[0] == 'Pushed to main in app'
    )


@pytest.mark.django_db
def test_details_are_fetched_once_and_missing_ones_are_skipped(user_service):
    service = GitHubService(user_service)
    not_found = httpclient.build_fetch_error(
        category='remote_4xx', detail='Not Found', status_code=404
    )
    with patch.object(service, '_get_json', side_effect=not_found) as get_json:
        assert service._detail('/repos/me/gone') is None
        assert service._detail('/repos/me/gone') is None
    assert get_json.call_count == 1


@pytest.mark.django_db
def test_a_rate_limit_while_fetching_details_stops_the_import(user_service):
    service = GitHubService(user_service)
    limited = httpclient.build_fetch_error(
        category='rate_limited', detail='limit', status_code=403, retryable=True
    )
    with (
        patch.object(service, '_get_json', side_effect=limited),
        pytest.raises(httpclient.FetchError),
    ):
        service._detail('/repos/me/app')


def test_titles_are_escaped_for_the_stream():
    entry = Entry(title='Released <x> of me/app')
    assert github.filter_title(entry) == 'Released &lt;x&gt; of me/app'


def test_urls_point_a_user_timeline_to_its_atom_feed():
    assert GitHubService(Service(api='github', user_id='me')).get_urls() == [
        'https://github.com/me.atom'
    ]
    assert GitHubService(Service(api='github')).get_urls() == []


def test_oauth_asks_for_no_scope():
    assert GitHubService(Service(api='github')).get_oauth_scopes() == []


def _store(service: Service, guid: str, active: bool = True) -> None:
    now = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    Entry.objects.create(
        service=service,
        guid=guid,
        title=guid,
        active=active,
        date_published=now,
        date_updated=now,
    )


def _active(service: Service) -> dict[str, bool]:
    return dict(Entry.objects.filter(service=service).values_list('guid', 'active'))


PUSH_GUID = 'tag:github.com,2008:PushEvent/1'
CREATE_GUID = 'tag:github.com,2008:CreateEvent/2'
RELEASE_GUID = 'https://github.com/me/app/releases/tag/v1'


def test_category_entries_find_entries_by_their_guid(user_service):
    _store(user_service, PUSH_GUID)
    _store(user_service, CREATE_GUID)
    _store(user_service, 'tag:github.com,2008:PublicEvent/3')
    _store(user_service, RELEASE_GUID)
    other = Service.objects.create(api='github', name='Other', user_id='you')
    _store(other, PUSH_GUID)

    def found(*categories: str) -> set[str]:
        entries = github.category_entries(user_service, categories)
        return set(entries.values_list('guid', flat=True))

    assert found('push') == {PUSH_GUID}
    assert found('repo') == {CREATE_GUID, 'tag:github.com,2008:PublicEvent/3'}
    assert found('release') == {RELEASE_GUID}
    assert found('push', 'release') == {PUSH_GUID, RELEASE_GUID}
    assert found() == set()


def test_unchecked_kinds_are_hidden_and_checked_ones_shown_again(user_service):
    _store(user_service, PUSH_GUID)
    _store(user_service, CREATE_GUID)
    _store(user_service, RELEASE_GUID, active=False)
    user_service.options = {github.OPTIONS_KEY: ['repo', 'release']}

    hidden, shown = github.show_enabled_entries(
        user_service, ('repo', 'release', 'push')
    )

    assert (hidden, shown) == (1, 0)
    # A release hidden by hand stays hidden: its kind was never unchecked.
    assert _active(user_service) == {
        PUSH_GUID: False,
        CREATE_GUID: True,
        RELEASE_GUID: False,
    }

    user_service.options = {github.OPTIONS_KEY: ['repo', 'push']}
    hidden, shown = github.show_enabled_entries(user_service, ('repo', 'release'))

    assert (hidden, shown) == (0, 1)
    assert _active(user_service) == {
        PUSH_GUID: True,
        CREATE_GUID: True,
        RELEASE_GUID: False,
    }
