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

// What the templates give the page script, as JSON in json_script elements
// (stream/templatetags/gls_page.py) rather than as inline script globals.

import type { PageConfig, StreamData } from './api-types';

/** #gls-config; a page without it keeps these defaults. */
export const config: PageConfig = {
    baseurl: '/',
    maps_engine: '',
    themes: [],
    lang: '',
    messages: {},
};

/** The value of the json_script element with this id, or null without one. */
function json_script(id: string): unknown {
    const text = document.getElementById(id)?.textContent;
    return text ? JSON.parse(text) : null;
}

/** Reads #gls-config into `config`. */
export function load_config(): void {
    Object.assign(config, json_script('gls-config') as Partial<PageConfig> | null);
}

/** #gls-stream-data of a stream page, or null on other pages. */
export function stream_data(): StreamData | null {
    return json_script('gls-stream-data') as StreamData | null;
}
