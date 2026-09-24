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

Pages the other E2E tests do not open, under the Content Security Policy.

The page fixture fails a test on anything the policy blocks, so each of these
only has to open the page and use it.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from glifestream.stream.models import Service

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def test_admin_runs_under_the_policy(
    page: Page, app_base_url: str, ensure_admin_session
):
    service = Service.objects.create(name='CSP Feed', api='webfeed', url='')
    ensure_admin_session()

    page.goto(f'{app_base_url}/admin/')
    expect(page.get_by_role('heading', name='Site administration')).to_be_visible()

    page.goto(f'{app_base_url}/admin/stream/service/{service.pk}/change/')
    expect(page.locator('#id_name')).to_have_value('CSP Feed')
    page.get_by_role('button', name='Save and continue editing').click()
    expect(page.locator('.messagelist')).to_contain_text('was changed successfully')
