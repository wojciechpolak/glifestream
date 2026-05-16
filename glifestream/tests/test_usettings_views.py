from datetime import timedelta
import pytest
from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone

from glifestream.stream.models import Service, List, ServiceFetchState


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
        last_result='Fetch failed.',
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
