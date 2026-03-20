import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from glifestream.stream.models import Service, List


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
    Service.objects.create(name='S1', api='webfeed', url='http://s1.com')
    response = logged_in_client.get(reverse('usettings-services'))
    assert response.status_code == 200
    assert 'S1' in response.content.decode()


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
        {'api': 'webfeed', 'name': 'Test Feed', 'url': 'http://test.com'},
    )
    assert response.status_code == 200
    data = response.json()
    assert data['name'] == 'Test Feed'
    assert 'fields' in data


@pytest.mark.django_db
def test_usettings_websub(logged_in_client):
    response = logged_in_client.get(reverse('usettings-websub'))
    assert response.status_code == 200

    # Mocking subscribe process would be complex, but we can check if it renders
    assert 'WebSub' in response.content.decode()
