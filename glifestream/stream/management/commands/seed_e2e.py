from __future__ import annotations

import datetime

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from glifestream.stream.models import Entry, List, Service

UTC = datetime.timezone.utc


class Command(BaseCommand):
    help = 'Seed deterministic services, entries, and lists for end-to-end tests.'

    def handle(self, *args, **options):
        try:
            admin_user = User.objects.get(username='admin')
        except User.DoesNotExist as exc:
            raise CommandError(
                'The admin user does not exist. Run create_initial_user first.'
            ) from exc

        private_service, _ = Service.objects.update_or_create(
            api='selfposts',
            name='Seeded Notes',
            defaults={
                'cls': 'notes',
                'display': 'both',
                'home': True,
                'active': True,
                'public': False,
                'url': '',
                'user_id': '',
                'link': '',
            },
        )

        Entry.objects.update_or_create(
            service=private_service,
            guid='seeded-private-entry',
            defaults={
                'title': 'Seeded Private Entry',
                'link': 'http://example.test/private-entry',
                'content': 'Private seeded content for Playwright coverage.',
                'date_published': datetime.datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
                'date_updated': datetime.datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
                'active': True,
                'draft': False,
                'friends_only': False,
            },
        )

        seeded_list, _ = List.objects.update_or_create(
            user=admin_user,
            slug='seeded-list',
            defaults={'name': 'Seeded List'},
        )
        seeded_list.services.set([private_service])

        self.stdout.write(
            self.style.SUCCESS(
                'Seeded deterministic E2E data for services, entries, and lists.'
            )
        )
