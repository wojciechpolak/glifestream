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
from urllib.parse import urlsplit
from uuid import uuid4

import jwt
from django.conf import settings


def make_magic_sso_token(
    *,
    email: str = 'friend@example.com',
    expires_at: datetime.datetime | None = None,
    audience: str = 'http://testserver',
    scope: str = 'friends',
    site_id: str = 'test-site',
) -> str:
    issued_at = datetime.datetime.now(datetime.timezone.utc)
    if expires_at is None:
        expires_at = issued_at + datetime.timedelta(minutes=5)

    server_url = urlsplit(
        getattr(settings, 'MAGICSSO_SERVER_URL', 'http://localhost:3000')
    )
    jwt_secret = getattr(
        settings, 'MAGICSSO_JWT_SECRET', 'VERY-VERY-LONG-RANDOM-JWT-SECRET'
    )
    issuer = f'{server_url.scheme}://{server_url.netloc}'
    payload = {
        'aud': audience,
        'email': email,
        'exp': expires_at,
        'iat': issued_at,
        'iss': issuer,
        'jti': str(uuid4()),
        'scope': scope,
        'siteId': site_id,
    }
    return jwt.encode(payload, jwt_secret, algorithm='HS256')
