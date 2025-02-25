"""
# gLifestream Copyright (C) 2025 Wojciech Polak
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from abc import ABC, abstractmethod
from glifestream.stream.models import Service


class BaseService(ABC):
    """
    The base interface for all service strategies.
    Each concrete service defines its logic in `run(...)`.
    """

    name: str
    limit_sec: int

    def __init__(self, service: Service, verbose: int = 0, force_overwrite: bool = False):
        self.service = service
        self.verbose = verbose
        self.force_overwrite = force_overwrite
        if self.verbose:
            print('%s: %s' % (self.name, self.service))

    @abstractmethod
    def run(self) -> None:
        pass
