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

/** Switches to the next theme, through the gls-theme cookie. */
export function change_theme(): boolean {
    const cookie_name = 'gls-theme';
    let cs = read_cookie(cookie_name);
    let idx = settings.themes.indexOf(cs as string);

    if (!cs || idx === -1) {
        idx = 0;
        cs = settings.themes[idx] as string;
    }
    if (idx < settings.themes.length - 1) {
        idx++;
    } else {
        idx = 0;
    }
    cs = settings.themes[idx] as string;
    write_cookie(cookie_name, cs, 365, config.baseurl);
    jump_to_top();
    reload_page();
    return false;
}
