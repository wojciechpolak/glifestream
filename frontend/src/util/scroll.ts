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

import { reduced_motion } from '../ui/fx';

function behavior(): ScrollBehavior {
    return reduced_motion() ? 'instant' : 'smooth';
}

/** Scrolls the page until `el` is `offset` pixels below the top. */
export function scroll_to_element(el: Element, offset = 16): void {
    const top = el.getBoundingClientRect().top + window.scrollY - (offset || 16);
    window.scrollTo({ top, behavior: behavior() });
}

export function scroll_to_top(): void {
    window.scrollTo({ top: 0, behavior: behavior() });
}

export function jump_to_top(): void {
    window.scrollTo({ top: 0, behavior: 'instant' });
}
