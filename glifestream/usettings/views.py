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
#
#  Compatibility facade for the split settings views.
"""

from glifestream.usettings.list_settings import lists
from glifestream.usettings.oauth_settings import oauth, oauth2
from glifestream.usettings.preferences_settings import preferences
from glifestream.usettings.service_settings import api, opml, services, status
from glifestream.usettings.websub_settings import websub

__all__ = [
    'api',
    'lists',
    'oauth',
    'oauth2',
    'opml',
    'preferences',
    'services',
    'status',
    'websub',
]
