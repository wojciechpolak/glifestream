/*
 *  gLifestream Copyright (C) 2009-2026 Wojciech Polak
 *
 *  This program is free software; you can redistribute it and/or modify it
 *  under the terms of the GNU General Public License as published by the
 *  Free Software Foundation; either version 3 of the License, or (at your
 *  option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

export function scroll_to_element(t: HTMLElement | JQuery, offset?: number): void {
    offset = offset || 16;
    const toffset = ($(t).offset() as JQuery.Coordinates).top - offset;
    $('html,body').animate(
        {
            scrollTop: toffset,
        },
        200,
    );
}

export function scroll_to_top(): void {
    $('html, body').animate({ scrollTop: 0 }, 'fast');
}

export function jump_to_top(): void {
    if (document.body && document.body.scrollTop) {
        document.body.scrollTop = 0;
    } else if (document.documentElement && document.documentElement.scrollTop) {
        document.documentElement.scrollTop = 0;
    }
}
