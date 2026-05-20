#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
#  gLifestream Copyright (C) 2009, 2010, 2014, 2015, 2021, 2023, 2026 Wojciech Polak
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

import os

import django

SITE_ROOT = os.path.dirname(os.path.realpath(__file__))
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    os.environ['DJANGO_SETTINGS_MODULE'] = 'glifestream.settings'

if hasattr(django, 'setup'):
    django.setup()

from glifestream.worker.cli import (  # noqa: E402
    _configure_library_logging,
    _preprocess_cli_args,
    main,
    run,
)
from glifestream.worker.daemon import WorkerDaemon  # noqa: E402
from glifestream.worker.maintenance import run_maintenance_args  # noqa: E402
from glifestream.worker.schedule import CronSchedule  # noqa: E402

__all__ = [
    'CronSchedule',
    'WorkerDaemon',
    '_configure_library_logging',
    '_preprocess_cli_args',
    'main',
    'run',
    'run_maintenance_args',
]


if __name__ == '__main__':
    run()
