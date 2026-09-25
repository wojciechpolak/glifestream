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
from glifestream.settings_csp import csp_settings
from glifestream.stream.models import Service
from glifestream.testsupport.coverage_report import (
    COVERAGE_HTML_DIR,
    COVERAGE_LCOV,
    coverage_enabled,
    describe_narrowed_run,
)


def pytest_configure(config: pytest.Config) -> None:
    del config
    from django.conf import settings

    # The default PBKDF2 hasher takes some 0.3 s a password by design. A browser
    # test hashes one to seed the admin, one to log in and more to change it.
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


@pytest.fixture(autouse=True)
def enforce_csp(settings):
    """Tests enforce the Content Security Policy, whatever the default.

    The E2E page fixture then fails a test on anything the policy blocks.
    """
    settings.SECURE_CSP, settings.SECURE_CSP_REPORT_ONLY = csp_settings(
        'enforce', static_url=settings.STATIC_URL
    )


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


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    del exitstatus
    if not coverage_enabled(config):
        return

    try:
        from coverage import Coverage
        from coverage.exceptions import CoverageException
    except ImportError:
        return

    narrowed = describe_narrowed_run(config)
    coverage = Coverage(config_file=True)
    try:
        coverage.load()
        if not narrowed:
            coverage.html_report(directory=COVERAGE_HTML_DIR)
            coverage.lcov_report(outfile=COVERAGE_LCOV)
        total = coverage.report(file=io.StringIO())
    except CoverageException:
        return

    terminalreporter.write_line(f'total coverage: {total:.2f}%')
    if narrowed:
        terminalreporter.write_line(
            'coverage.lcov and htmlcov/ kept from the last full run '
            '(%s ran a subset)' % narrowed
        )
