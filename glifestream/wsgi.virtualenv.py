#  gLifestream Copyright (C) 2013, 2014 Wojciech Polak
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
#  with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import site
from django.core.wsgi import get_wsgi_application


SITE_ROOT = os.path.dirname(os.path.realpath(__file__))
os.environ['DJANGO_SETTINGS_MODULE'] = 'glifestream.settings'

python_home = os.path.join(SITE_ROOT, '..')
python_version = '.'.join(map(str, sys.version_info[:2]))  # pylint: disable=all
site_packages = python_home + '/lib/python%s/site-packages' % python_version
site.addsitedir(site_packages)

sys.path.insert(0, os.path.join(SITE_ROOT, '../'))

application = get_wsgi_application()
