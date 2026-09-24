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

/** Shows the busy spinner after `el`; there is one at a time. */
export function show_spinner(el: Element): void {
    const span = document.createElement('span');
    span.id = 'spinner';
    if (el instanceof HTMLElement) {
        el.blur();
    }
    el.after(span);
}

export function hide_spinner(): void {
    document.getElementById('spinner')?.remove();
}
