"""
#  gLifestream Copyright (C) 2009-2026 Wojciech Polak
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

from glifestream.apis.base import BaseService
from glifestream.filters import twyntax
from glifestream.stream.models import Entry


class TwitterService(BaseService):
    """Defunct: the v1.1 endpoints this fetched from are gone.

    Kept so that stored ``Service.api == 'twitter'`` rows still resolve and
    their entries keep rendering. The OAuth URLs stay because
    ``gauth.gls_oauth.OAuth1Client`` reads them off the api object.
    """

    name = 'Twitter API v1.1 (defunct)'
    limit_sec = 120

    OAUTH_REQUEST_TOKEN_URL = 'https://api.twitter.com/oauth/request_token'
    OAUTH_AUTHORIZE_URL = 'https://api.twitter.com/oauth/authorize'
    OAUTH_ACCESS_TOKEN_URL = 'https://api.twitter.com/oauth/access_token'

    def get_urls(self) -> list[str]:
        return []

    def run(self) -> None:
        pass


def filter_content(entry: Entry) -> str:
    return twyntax.parse(entry.content)
