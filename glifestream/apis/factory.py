"""
#  gLifestream Copyright (C) 2025 Wojciech Polak
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

from glifestream.apis.atproto import AtProtoService
from glifestream.apis.base import BaseService
from glifestream.apis.flickr import FlickrService
from glifestream.apis.friendfeed import FriendFeedService
from glifestream.apis.mastodon import MastodonService
from glifestream.apis.pixelfed import PixelFedService
from glifestream.apis.pocket import PocketService
from glifestream.apis.selfposts import SelfpostsService
from glifestream.apis.twitter import TwitterService
from glifestream.apis.vimeo import VimeoService
from glifestream.apis.webfeed import WebfeedService
from glifestream.apis.youtube import YoutubeService
from glifestream.stream.models import Service

SERVICE_CLASSES = {
    'atproto': AtProtoService,
    'flickr': FlickrService,
    'friendfeed': FriendFeedService,
    'mastodon': MastodonService,
    'pixelfed': PixelFedService,
    'pocket': PocketService,
    'selfposts': SelfpostsService,
    'twitter': TwitterService,
    'vimeo': VimeoService,
    'webfeed': WebfeedService,
    'youtube': YoutubeService,
}


class ServiceFactory:
    """
    Creates a concrete Service.
    """

    @staticmethod
    def create_service(
        service: Service, verbose: int = 0, force_overwrite: bool = False
    ) -> BaseService:
        service_class = ServiceFactory.get_service_class(service.api)
        return service_class(service, verbose, force_overwrite)

    @staticmethod
    def get_service_class(api_name: str) -> type[BaseService]:
        try:
            return SERVICE_CLASSES[api_name]
        except KeyError as exc:
            raise ValueError(f'Unknown service API: {api_name}') from exc
