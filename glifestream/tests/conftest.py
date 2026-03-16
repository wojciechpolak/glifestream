import pytest
from django.contrib.auth.models import User
from glifestream.stream.models import Service


@pytest.fixture
def user(db):
    return User.objects.create_user(username='testuser', password='password')


@pytest.fixture
def service(db):
    s = Service(
        name='Test Service', api='feed', url='http://example.com/feed', public=True
    )
    s.save()
    return s
