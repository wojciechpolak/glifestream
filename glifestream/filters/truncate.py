"""
#  gLifestream Copyright (C) 2009, 2010, 2013, 2023 Wojciech Polak
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


def simple(content: str, max_length: int = 36, suffix: str = '...') -> str:
    content = content.strip()
    if len(content) <= max_length:
        return content
    content = content[:max_length].rsplit(' ', 1)[0].rstrip(' -/,:.')
    return content + suffix


def smart(content: str, max_words: int = 7,
          max_length: int = 36, suffix: str = '...') -> str:
    sx = ''
    content = content.strip()
    words = content.split(' ')
    if len(words) > max_words:
        content = ' '.join(words[:max_words])
        sx = suffix
    if len(content) <= max_length:
        return content.rstrip(' -/,:.') + sx
    content = content[:max_length].rsplit(' ', 1)[0].rstrip(' -/,:.')
    return content + suffix
