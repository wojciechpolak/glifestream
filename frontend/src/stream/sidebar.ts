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

import { config } from '../config';
import { read_cookie, write_cookie } from '../util/cookies';
import { delegate } from '../util/dom';
import { reload_page } from '../util/navigation';
import { jump_to_top } from '../util/scroll';

/** Shows or hides reblogs, through the gls-reblogs cookie. */
export function toggle_reblogs(): boolean {
    const cookie_name = 'gls-reblogs';
    let val = read_cookie(cookie_name);
    val = !+(val as string) ? '1' : '0';
    write_cookie(cookie_name, val, 365, config.baseurl);
    reload_page();
    return false;
}

/** The list of themes over "Change theme", when there are more than two. */
function theme_menu(): HTMLElement | null {
    return document.getElementById('theme-menu');
}

function set_theme_menu_open(open: boolean): void {
    theme_menu()?.classList.toggle('menu-expanded', open);
    document
        .getElementById('change-theme')
        ?.setAttribute('aria-expanded', String(open));
}

/** Switches to the theme `name`, through the gls-theme cookie. */
function use_theme(name: string): void {
    write_cookie('gls-theme', name, 365, config.baseurl);
    jump_to_top();
    reload_page();
}

/** Opens or closes the list of themes, or with no list, switches to the
 * next theme. */
export function change_theme(): boolean {
    const menu = theme_menu();
    if (menu) {
        set_theme_menu_open(!menu.classList.contains('menu-expanded'));
        return false;
    }
    const current = config.themes.indexOf(read_cookie('gls-theme') as string);
    // A visitor without the cookie is on the first theme.
    const next = (Math.max(current, 0) + 1) % config.themes.length;
    use_theme(config.themes[next] as string);
    return false;
}

/** Makes the list of themes pick one, and close on a click elsewhere or on
 * Escape. */
export function init_theme_menu(): void {
    const menu = theme_menu();
    if (!menu) {
        return;
    }
    delegate(menu, 'click', '[data-theme]', function (choice) {
        set_theme_menu_open(false);
        if (choice.getAttribute('aria-current') === 'true') {
            document.getElementById('change-theme')?.focus();
        } else {
            use_theme(choice.dataset['theme'] as string);
        }
        return false;
    });
    document.addEventListener('click', function (event) {
        const wrapper = menu.parentElement;
        if (
            menu.classList.contains('menu-expanded') &&
            event.target instanceof Node &&
            !wrapper?.contains(event.target)
        ) {
            set_theme_menu_open(false);
        }
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && menu.classList.contains('menu-expanded')) {
            set_theme_menu_open(false);
            document.getElementById('change-theme')?.focus();
        }
    });
}
