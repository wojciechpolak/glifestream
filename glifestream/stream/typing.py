#  gLifestream Copyright (C) 2023 Wojciech Polak
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

from typing import TypedDict, Any


class Page(TypedDict, total=False):
    after: int
    author_name: str
    author_uri: str
    backtime: bool
    base_url: str
    canonical_link: str
    copyright_years: str
    ctx: str
    description: str
    exactentry: bool
    favicon: str
    favorites: bool
    icon: str
    lang: str
    login_url: str
    maps_engine: str
    month_nav: bool
    month_next: str
    month_prev: str
    months12: Any
    nextpage: int
    prevpage: int
    pshb_hubs: str
    public: bool
    pwa: str
    revision: str
    robots: str
    search: str
    site_url: str
    start: int
    subtitle: str
    taguri: str
    theme: str
    themes: list[str] | tuple[str]
    themes_more: bool
    title: str
    updated: Any
    urlparams: str
    version: str


class ThumbInfo(TypedDict):
    local: str
    url: str
    rel: str
    internal: str
