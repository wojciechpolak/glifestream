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

/** How much of the window's top a pinned top bar covers: the themes pin
 *  #head at narrow widths. */
export function pinned_head_height(): number {
    const head = document.getElementById('head');
    if (!head || getComputedStyle(head).position !== 'fixed') {
        return 0;
    }
    return Math.max(0, head.getBoundingClientRect().bottom);
}

/** Scrolls the page until `el` is `offset` pixels below the top, or below
 *  a pinned top bar. */
export function scroll_to_element(el: Element, offset = 16): void {
    const top =
        el.getBoundingClientRect().top +
        window.scrollY -
        (offset || 16) -
        pinned_head_height();
    window.scrollTo({ top, behavior: behavior() });
}

export function scroll_to_top(): void {
    window.scrollTo({ top: 0, behavior: behavior() });
}

export function jump_to_top(): void {
    window.scrollTo({ top: 0, behavior: 'instant' });
}
