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

import pytest
from django.contrib.auth.models import User
from django.urls import reverse


@pytest.fixture
def owner(db):
    return User.objects.create_user(username='owner', password='pw', is_staff=True)


def log_in(client, next_url, *, in_query=False):
    data = {'username': 'owner', 'password': 'pw'}
    url = reverse('login')
    if in_query:
        url += '?next=%s' % next_url
    else:
        data['next'] = next_url
    return client.post(url, data)


@pytest.mark.django_db
@pytest.mark.parametrize('in_query', [False, True])
def test_login_returns_to_the_page_that_asked_for_it(client, owner, in_query):
    response = log_in(client, '/settings/services', in_query=in_query)

    assert response.status_code == 302
    assert response['Location'] == '/settings/services'


@pytest.mark.django_db
@pytest.mark.parametrize(
    'next_url',
    [
        'https://evil.example/',
        '//evil.example/',
        '/\\evil.example/',
        'http:evil.example',
        'javascript:alert(1)',
    ],
)
def test_login_never_redirects_off_site(client, owner, next_url):
    response = log_in(client, next_url)

    assert response.status_code == 302
    assert response['Location'] == reverse('index')


@pytest.mark.django_db
def test_login_form_carries_only_a_safe_next(client):
    response = client.get(reverse('login'), {'next': '//evil.example/'})

    assert response.context['next'] == reverse('index')
