from datetime import timedelta
from typing import Any, cast
import pytest
from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import JsonResponse
from django.test import RequestFactory
from django.utils import timezone

from glifestream.stream.models import Service, List, ServiceFetchState
from glifestream.usettings import service_settings


@pytest.fixture
def staff_user(db):
    user = User.objects.create_user(
        username='staff', password='password', is_staff=True
    )
    return user


@pytest.fixture
def logged_in_client(client, staff_user):
    client.login(username='staff', password='password')
    return client


@pytest.mark.django_db
def test_usettings_services_access(client, staff_user):
    # Test that non-staff cannot access
    User.objects.create_user(username='user', password='password', is_staff=False)
    client.login(username='user', password='password')
    response = client.get(reverse('usettings-services'))
    assert response.status_code == 403


@pytest.mark.django_db
def test_usettings_services_list(logged_in_client):
    service = Service.objects.create(name='S1', api='webfeed', url='http://s1.com')
    ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_FAILED,
        finished_at=timezone.now(),
        last_failed_at=timezone.now(),
        last_error='feed timeout',
    )
    response = logged_in_client.get(reverse('usettings-services'))
    assert response.status_code == 200
    body = response.content.decode()
    assert 'S1' in body
    assert 'Last successful import' not in body
    assert 'Last completed attempt' not in body
    assert 'Next scheduled fetch' not in body
    assert 'feed timeout' not in body
    assert 'Run now' not in body
    assert 'fetch-status-' not in body


@pytest.mark.django_db
def test_usettings_status_list(logged_in_client):
    service = Service.objects.create(name='S1', api='webfeed', url='http://s1.com')
    succeeded_at = timezone.now() - timedelta(hours=1)
    ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_FAILED,
        finished_at=timezone.now(),
        last_succeeded_at=succeeded_at,
        last_failed_at=timezone.now(),
        last_result='Remote request timed out.',
        last_error='feed timeout',
    )
    response = logged_in_client.get(reverse('usettings-status'))
    assert response.status_code == 200
    body = response.content.decode()
    assert 'Service fetch status' in body
    assert 'S1' in body
    assert 'Last successful import' in body
    assert 'Last completed attempt' in body
    assert 'Next scheduled fetch' in body
    assert 'feed timeout' in body
    assert 'Remote request timed out.' in body
    assert 'data-last-failed-at=' in body
    assert 'Run now' in body
    assert 'fetch-status-' in body


@pytest.mark.django_db
def test_usettings_status_hides_non_fetchable_services(logged_in_client):
    Service.objects.create(name='Notes', api='selfposts')

    response = logged_in_client.get(reverse('usettings-status'))

    assert response.status_code == 200
    assert 'No fetchable services are connected yet.' in response.content.decode()


@pytest.mark.django_db
def test_usettings_services_list_legacy_unknown_api_does_not_crash(logged_in_client):
    Service.objects.create(name='Legacy Facebook', api='fb', url='http://s1.com')
    response = logged_in_client.get(reverse('usettings-services'))
    assert response.status_code == 200
    body = response.content.decode()
    assert 'Legacy Facebook' in body
    assert 'class="run-fetch"' not in body


@pytest.mark.django_db
def test_usettings_lists_management(logged_in_client, staff_user):
    # GET
    response = logged_in_client.get(reverse('usettings-lists'))
    assert response.status_code == 200

    # CREATE
    srv = Service.objects.create(name='S1', api='webfeed')
    response = logged_in_client.post(
        reverse('usettings-lists'), {'name': 'New List', 'services': [srv.pk]}
    )
    assert response.status_code == 302
    assert List.objects.filter(name='New List', user=staff_user).exists()

    # UPDATE
    List.objects.get(slug='new-list')
    response = logged_in_client.post(
        reverse('usettings-lists-slug', args=['new-list']),
        {'name': 'Updated List', 'services': [srv.pk]},
    )
    assert response.status_code == 302
    assert List.objects.filter(name='Updated List').exists()

    # DELETE
    response = logged_in_client.post(
        reverse('usettings-lists-slug', args=['updated-list']), {'delete': '1'}
    )
    assert response.status_code == 302
    assert not List.objects.filter(slug='updated-list').exists()


@pytest.mark.django_db
def test_usettings_api_json(logged_in_client):
    # Test XHR API for service settings
    response = logged_in_client.post(
        reverse('usettings-api-cmd', args=['service']),
        {
            'api': 'webfeed',
            'name': 'Test Feed',
            'url': 'http://test.com',
            'method': 'post',
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data['name'] == 'Test Feed'
    assert data['method'] == 'post'
    assert 'fields' in data


@pytest.mark.django_db
def test_usettings_service_api_sets_need_import_only_for_new_fetchable_services(
    logged_in_client,
):
    response = logged_in_client.post(
        reverse('usettings-api-cmd', args=['service']),
        {
            'api': 'webfeed',
            'name': 'Fetchable Feed',
            'url': 'https://example.com/feed.xml',
            'method': 'post',
        },
    )

    assert response.status_code == 200
    assert response.json()['need_import'] is True

    response = logged_in_client.post(
        reverse('usettings-api-cmd', args=['service']),
        {
            'api': 'selfposts',
            'name': 'Notes',
            'method': 'post',
        },
    )

    assert response.status_code == 200
    assert response.json()['need_import'] is False


@pytest.mark.django_db
def test_usettings_fetch_now_and_status(logged_in_client):
    service = Service.objects.create(name='S1', api='webfeed', url='http://s1.com')

    with patch('glifestream.fetching.send_worker_wake_signal', return_value=True):
        response = logged_in_client.post(
            reverse('usettings-api-cmd', args=['fetch-now']),
            {'id': service.pk},
        )

    assert response.status_code == 200
    data = response.json()
    assert data['queued'] is True
    assert data['state']['status'] == 'queued'
    assert 'last_succeeded_at' in data['state']
    assert 'last_failed_at' in data['state']

    response = logged_in_client.get(reverse('usettings-api-cmd', args=['fetch-status']))
    assert response.status_code == 200
    data = response.json()
    assert str(service.pk) in data['services']
    assert 'last_succeeded_at' in data['services'][str(service.pk)]
    assert 'last_failed_at' in data['services'][str(service.pk)]
    assert 'max-age=0' in response.headers['Cache-Control']


@pytest.mark.django_db
def test_usettings_fetch_status_exposes_failure_state(logged_in_client):
    service = Service.objects.create(name='S1', api='webfeed', url='http://s1.com')
    failed_at = timezone.now()
    succeeded_at = failed_at - timedelta(hours=2)
    ServiceFetchState.objects.create(
        service=service,
        status=ServiceFetchState.STATUS_FAILED,
        finished_at=failed_at,
        last_succeeded_at=succeeded_at,
        last_failed_at=failed_at,
        last_result='Remote service returned a temporary server error.',
        last_error='remote 500',
    )

    response = logged_in_client.get(
        reverse('usettings-api-cmd', args=['fetch-status']),
        {'id': str(service.pk)},
    )

    assert response.status_code == 200
    state = response.json()['services'][str(service.pk)]
    assert state['status'] == 'failed'
    assert state['last_error'] == 'remote 500'
    assert state['last_succeeded_at'] == succeeded_at.isoformat()
    assert state['last_failed_at'] == failed_at.isoformat()


@pytest.mark.django_db
def test_usettings_websub(logged_in_client):
    response = logged_in_client.get(reverse('usettings-websub'))
    assert response.status_code == 200

    # Mocking subscribe process would be complex, but we can check if it renders
    assert 'WebSub' in response.content.decode()


@pytest.mark.django_db
def test_usettings_api_dispatches_through_registry(logged_in_client, monkeypatch):
    called = {}

    def fake_handler(request, user, cmd, id_service):
        called['cmd'] = cmd
        called['id_service'] = id_service
        return JsonResponse({'ok': True})

    monkeypatch.setitem(service_settings.SERVICE_API_HANDLERS, 'service', fake_handler)

    response = logged_in_client.post(
        reverse('usettings-api-cmd', args=['service']),
        {'id': '17'},
    )

    assert response.status_code == 200
    assert response.json() == {'ok': True}
    assert called == {'cmd': 'service', 'id_service': '17'}


def test_validate_service_payload_preserves_missing_field_behavior():
    request = RequestFactory().post(
        '/settings/api/service',
        {'timeline': 'user'},
    )
    payload = {
        'api': 'mastodon',
        'name': '',
        'cls': '',
        'url': '',
        'user_id': '',
        'fetch_interval_sec': '-5',
        'display': 'content',
        'public': False,
        'home': False,
        'active': False,
        'id': None,
    }

    method, miss, fetch_interval = service_settings.validate_service_payload(
        payload, request, 'post'
    )

    assert method == 'get'
    assert miss == {
        'name': True,
        'fetch_interval_sec': True,
        'user_id': True,
    }
    assert fetch_interval == -5


@pytest.mark.django_db
def test_handle_opml_import_file_normalizes_supported_feed_urls():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <body>
    <outline text="Videos">
      <outline type="rss" text="Channel Feed" xmlUrl="http://vimeo.com/channels/staffpicks/videos/rss" />
    </outline>
  </body>
</opml>
"""

    service_settings.handle_opml_import_file(xml)

    service = Service.objects.get(name='Channel Feed')
    assert service.api == 'vimeo'
    assert service.url == 'channel/staffpicks'
    assert service.cls == 'videos'
    assert service.display == 'both'


@pytest.mark.django_db
def test_get_fetchable_services_excludes_non_fetchable_and_decorates():
    fetchable = Service.objects.create(name='Feed', api='webfeed', url='http://s1.com')
    Service.objects.create(name='Notes', api='selfposts')
    ServiceFetchState.objects.create(service=fetchable)

    services = list(
        Service.objects.select_related('fetch_state').all().order_by('name')
    )
    fetchable_services = service_settings.get_fetchable_services(services)

    assert [service.name for service in fetchable_services] == ['Feed']
    assert cast(Any, services[0]).fetch_state_snapshot['can_fetch'] is True
    assert cast(Any, services[1]).fetch_state_snapshot['can_fetch'] is False


# ------------------------------------------------------------------- websub


@pytest.mark.django_db
def test_websub_settings_list_excludes_apis_that_cannot_subscribe(logged_in_client):
    Service.objects.create(name='Feed', api='webfeed', url='http://s1.com')
    Service.objects.create(name='Toots', api='mastodon', url='http://s2.com')

    body = logged_in_client.get(reverse('usettings-websub')).content.decode()

    assert 'Feed' in body
    assert 'Toots' not in body


@pytest.mark.django_db
@pytest.mark.parametrize(
    'result,expected',
    [
        ({'rc': 1, 'error': 'hub refused'}, 'hub refused'),
        ({'rc': 2}, 'Hub not found.'),
        (
            {'rc': 202, 'hub': 'http://hub'},
            'Hub http://hub: Accepted for verification.',
        ),
        ({'rc': 204, 'hub': 'http://hub'}, 'Hub http://hub: Subscription verified.'),
    ],
)
def test_websub_settings_subscribe_reports_each_outcome(
    logged_in_client, result, expected
):
    service = Service.objects.create(name='Feed', api='webfeed', url='http://s1.com')

    with patch('glifestream.stream.websub.subscribe', return_value=result):
        response = logged_in_client.post(
            reverse('usettings-websub'), {'subscribe': str(service.pk)}
        )

    assert response.context['page']['msg'] == expected


@pytest.mark.django_db
def test_websub_settings_subscribe_says_nothing_about_an_unremarkable_code(
    logged_in_client,
):
    service = Service.objects.create(name='Feed', api='webfeed', url='http://s1.com')

    with patch('glifestream.stream.websub.subscribe', return_value={'rc': 200}):
        response = logged_in_client.post(
            reverse('usettings-websub'), {'subscribe': str(service.pk)}
        )

    assert 'msg' not in response.context['page']


@pytest.mark.django_db
@pytest.mark.parametrize(
    'result,expected',
    [
        ({'rc': 1}, 'No subscription found.'),
        (
            {'rc': 202, 'hub': 'http://hub'},
            'Hub http://hub: Accepted for verification.',
        ),
        ({'rc': 204, 'hub': 'http://hub'}, 'Hub http://hub: Unsubscribed.'),
        ({'rc': 'timed out', 'hub': 'http://hub'}, 'Hub http://hub: timed out.'),
    ],
)
def test_websub_settings_unsubscribe_reports_each_outcome(
    logged_in_client, result, expected
):
    with patch('glifestream.stream.websub.unsubscribe', return_value=result) as unsub:
        response = logged_in_client.post(
            reverse('usettings-websub'), {'unsubscribe': '7'}
        )

    unsub.assert_called_once_with('7')
    assert response.context['page']['msg'] == expected


# --------------------------------------------------------------------- opml


@pytest.mark.django_db
def test_opml_import_creates_the_services_and_redirects(logged_in_client):
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <body>
    <outline type="rss" text="Plain Feed" xmlUrl="http://example.com/rss" />
  </body>
</opml>
"""
    upload = SimpleUploadedFile('feeds.opml', xml, content_type='text/xml')

    response = logged_in_client.post(reverse('opml-import'), {'opml': upload})

    assert response.status_code == 302
    assert response['Location'] == reverse('usettings-services')
    assert Service.objects.get(name='Plain Feed').api == 'webfeed'


@pytest.mark.django_db
def test_opml_import_without_a_file_just_redirects(logged_in_client):
    response = logged_in_client.post(reverse('opml-import'))

    assert response.status_code == 302
    assert not Service.objects.exists()


@pytest.mark.django_db
def test_opml_export_offers_every_service_url_as_an_attachment(logged_in_client):
    Service.objects.create(name='Feed', api='webfeed', url='http://example.com/rss')
    Service.objects.create(name='Notes', api='selfposts')

    response = logged_in_client.get(reverse('opml-export'))

    body = response.content.decode()
    assert response['Content-Type'] == 'text/xml'
    assert response['Content-Disposition'] == 'attachment; filename="gls-services.xml"'
    assert 'http://example.com/rss' in body
    assert 'Notes' not in body


@pytest.mark.django_db
def test_opml_export_skips_a_service_whose_api_no_longer_exists(logged_in_client):
    Service.objects.create(name='Feed', api='webfeed', url='http://example.com/rss')
    Service.objects.create(name='Gone', api='no-such-api', url='http://gone/rss')

    body = logged_in_client.get(reverse('opml-export')).content.decode()

    assert 'http://example.com/rss' in body
    assert 'Gone' not in body


@pytest.mark.django_db
def test_opml_with_an_unknown_command_is_an_empty_response(logged_in_client):
    request = RequestFactory().get('/settings/services/whatever')
    request.user = User.objects.get(username='staff')

    response = service_settings.opml(request, cmd='nonsense')

    assert response.status_code == 200
    assert response.content == b''


@pytest.mark.django_db
def test_opml_import_reads_a_nested_category_as_the_service_class(logged_in_client):
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <body>
    <outline text="Photos">
      <outline type="rss" title="Album" xmlUrl="http://example.com/album" />
    </outline>
  </body>
</opml>
"""

    service_settings.handle_opml_import_file(xml)

    assert Service.objects.get(name='Album').cls == 'photos'


# ------------------------------------------------------- import URL rewriting


@pytest.mark.parametrize(
    'url,expected',
    [
        (
            'http://api.flickr.com/services/feeds/photos_public.gne?id=12345@N00',
            ('12345@N00', 'flickr', 'photos'),
        ),
        (
            'http://flickr.com/feed?format=atom',
            ('http://flickr.com/feed?format=rss_200', 'flickr', 'photos'),
        ),
        (
            'http://twitter.com/1/statuses/user_timeline/bob.rss',
            ('bob', 'twitter', 'sms'),
        ),
        (
            'http://vimeo.com/channels/staffpicks/videos/rss',
            ('channel/staffpicks', 'vimeo', 'videos'),
        ),
        (
            'http://vimeo.com/groups/hd/videos/rss',
            ('group/hd', 'vimeo', 'videos'),
        ),
        (
            'http://gdata.youtube.com/feeds/api/users/bob',
            ('bob', 'youtube', 'videos'),
        ),
        (
            'http://youtube.com/feeds/videos.xml?channel_id=x',
            ('http://youtube.com/feeds/videos.xml?channel_id=x', 'youtube', 'videos'),
        ),
        (
            'http://yelp.com/syndicate/user/bob',
            ('http://yelp.com/syndicate/user/bob', 'yelp', 'reviews'),
        ),
        (
            'http://example.com/rss',
            ('http://example.com/rss', 'webfeed', 'webfeed'),
        ),
    ],
)
def test_import_rules_rewrite_known_hosts(url, expected):
    assert service_settings._apply_import_rules(url, 'webfeed') == expected


@pytest.mark.parametrize(
    'url',
    [
        'http://twitter.com/bob',
        'http://vimeo.com/some/other/page',
    ],
)
def test_import_rules_leave_an_unrecognised_path_as_a_plain_webfeed(url):
    assert service_settings._apply_import_rules(url, 'webfeed') == (
        url,
        'webfeed',
        'webfeed',
    )


@pytest.mark.django_db
def test_normalize_imported_service_does_not_duplicate_an_existing_service():
    service_settings.normalize_imported_service('http://example.com/rss', 'Feed')
    service_settings.normalize_imported_service('http://example.com/rss', 'Renamed')

    assert Service.objects.filter(url='http://example.com/rss').count() == 1
    assert Service.objects.get(url='http://example.com/rss').name == 'Feed'


@pytest.mark.django_db
def test_normalize_imported_service_shows_content_only_for_photo_feeds():
    service_settings.normalize_imported_service(
        'http://api.flickr.com/services/feeds/photos_public.gne?id=12345@N00', 'Pics'
    )

    assert Service.objects.get(name='Pics').display == 'content'


@pytest.mark.django_db
def test_normalize_imported_service_swallows_a_bad_row():
    with patch.object(service_settings.Service, 'save', side_effect=Exception('nope')):
        service_settings.normalize_imported_service('http://example.com/rss', 'Feed')

    assert not Service.objects.exists()
