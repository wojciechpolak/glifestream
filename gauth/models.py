#  gLifestream Copyright (C) 2010 Wojciech Polak
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

from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext as _

class OpenId (models.Model):
    user = models.ForeignKey (User, db_index=True)
    identity = models.CharField (_('Identity'), max_length=128, null=False,
                                 blank=False)
    class Meta:
        verbose_name = 'OpenID'
        verbose_name_plural = 'OpenID'
        ordering = 'user',
        unique_together = (('user', 'identity'),)

    def __unicode__ (self):
        return u'%s: %s' % (self.user, self.identity)
