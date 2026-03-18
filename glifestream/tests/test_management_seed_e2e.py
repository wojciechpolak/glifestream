from django.contrib.auth.models import User
from django.core.management import call_command

import pytest

from glifestream.stream.models import Entry, List, Service


@pytest.mark.django_db
def test_seed_e2e_creates_expected_data():
    call_command('create_initial_user')
    call_command('seed_e2e')

    admin_user = User.objects.get(username='admin')
    service = Service.objects.get(name='Seeded Notes')
    entry = Entry.objects.get(guid='seeded-private-entry')
    seeded_list = List.objects.get(user=admin_user, slug='seeded-list')

    assert service.api == 'selfposts'
    assert entry.service == service
    assert seeded_list.name == 'Seeded List'
    assert list(seeded_list.services.all()) == [service]


@pytest.mark.django_db
def test_seed_e2e_is_idempotent():
    call_command('create_initial_user')
    call_command('seed_e2e')
    call_command('seed_e2e')

    assert Service.objects.filter(name='Seeded Notes').count() == 1
    assert Entry.objects.filter(guid='seeded-private-entry').count() == 1
    assert List.objects.filter(slug='seeded-list').count() == 1
