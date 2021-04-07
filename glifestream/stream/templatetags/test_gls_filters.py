#  gLifestream Copyright (C) 2021 Wojciech Polak
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

from unittest import TestCase
from .gls_filters import fix_ampersands


class Test(TestCase):
    def test_fix_ampersands(self):
        self.assertEquals(fix_ampersands(''), '')
        self.assertEquals(fix_ampersands('&'), '&amp;')
        self.assertEquals(fix_ampersands('a&b'), 'a&amp;b')
        self.assertEquals(fix_ampersands('a & b'), 'a &amp; b')
        self.assertEquals(fix_ampersands('a & b &amp;'), 'a &amp; b &amp;')
        self.assertEquals(fix_ampersands('Fast&Fun;'), 'Fast&amp;Fun;')
