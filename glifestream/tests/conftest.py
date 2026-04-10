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

import io

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


def _coverage_enabled(config: pytest.Config) -> bool:
    return not bool(getattr(config.option, 'no_cov', False)) and bool(
        getattr(config.option, 'cov_source', None)
        or getattr(config.option, 'cov_report', None)
    )


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    del exitstatus
    if not _coverage_enabled(config):
        return

    try:
        from coverage import Coverage
        from coverage.exceptions import CoverageException
    except ImportError:
        return

    coverage = Coverage(config_file=True)
    try:
        coverage.load()
        coverage.html_report(directory='htmlcov')
        coverage.lcov_report(outfile='coverage.lcov')
        total = coverage.report(file=io.StringIO())
    except CoverageException:
        return

    terminalreporter.write_line(f'total coverage: {total:.2f}%')
