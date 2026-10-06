/*
 *  gLifestream Copyright (C) 2026 Wojciech Polak
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

// The menu button of the top bar. On a narrow screen the theme folds the
// greeting and the links into a panel the button opens; wider, it hides the
// button and nothing here runs.

import { listen } from '../util/dom';

/** The width from which the theme shows the links in the bar again. */
const WIDE_SCREEN = '(min-width: 921px)';

function set_open(nav: HTMLElement, toggle: HTMLElement, open: boolean): void {
    nav.classList.toggle('open', open);
    toggle.setAttribute('aria-expanded', String(open));
}

export function init_navtop(): void {
    const nav = document.getElementById('navtop');
    const toggle = document.getElementById('navtop-toggle');
    if (!nav || !toggle) {
        return;
    }

    listen(toggle, 'click', function () {
        set_open(nav, toggle, !nav.classList.contains('open'));
        return false;
    });

    // A click anywhere else closes the menu.
    document.addEventListener('click', function (event) {
        if (
            nav.classList.contains('open') &&
            event.target instanceof Node &&
            !nav.contains(event.target)
        ) {
            set_open(nav, toggle, false);
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && nav.classList.contains('open')) {
            set_open(nav, toggle, false);
            toggle.focus();
        }
    });

    // A menu left open would come back when the screen narrows again.
    if (typeof window.matchMedia === 'function') {
        window.matchMedia(WIDE_SCREEN).addEventListener('change', function (query) {
            if (query.matches) {
                set_open(nav, toggle, false);
            }
        });
    }
}
