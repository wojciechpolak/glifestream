import pytest
from django.core.management import call_command

from glifestream.stream.models import Entry, Service


@pytest.mark.django_db
def test_loads_services_and_welcome_entry():
    call_command('load_initial_data', verbosity=0)

    assert Service.objects.filter(api='selfposts').count() == 6
    entry = Entry.objects.get()
    assert entry.pk == 1
    assert entry.service.cls == 'blog'
    assert 'data-id="youtube-SkVqJ1SGeL0"' in entry.content


@pytest.mark.django_db
def test_no_welcome_loads_only_services():
    call_command('load_initial_data', '--no-welcome', verbosity=0)

    assert Service.objects.count() == 6
    assert not Entry.objects.exists()


@pytest.mark.django_db
def test_leaves_a_database_with_services_alone(service):
    call_command('load_initial_data', verbosity=0)

    assert list(Service.objects.all()) == [service]
    assert not Entry.objects.exists()


@pytest.mark.django_db
def test_welcome_entry_shows_a_video_card(client):
    call_command('load_initial_data', verbosity=0)

    html = client.get('/entry/1', follow=True).content.decode()

    assert 'Hello, World!' in html
    assert 'data-id="youtube-SkVqJ1SGeL0" class="play-video"' in html
