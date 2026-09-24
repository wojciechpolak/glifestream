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

import type { StreamPage } from '../api-types';
import { get_json } from '../http';
import { Lightbox } from '../ui/lightbox';
import { hide_spinner, show_spinner } from '../ui/spinner';
import { follow_href } from '../util/navigation';
import { scroll_to_element } from '../util/scroll';
import { scaledown_images } from './images';
import { render_maps } from './maps';
import { alter_html } from './media';
import { stream_state } from './state';

/** "Next" links with a page on its way. */
const busy = new WeakSet<HTMLAnchorElement>();

/** Points a "next" link at the page after `next`, or drops it at the end. */
function advance(link: HTMLAnchorElement, next: StreamPage['next']): void {
    let s = link.href.indexOf('start=');
    if (s !== -1 && next) {
        link.href = link.href.substring(0, s + 6) + next;
        return;
    }
    s = link.href.indexOf('page=');
    if (s !== -1 && next) {
        link.href = link.href.substring(0, s + 5) + next;
        return;
    }
    link.remove();
}

function all_articles(): HTMLElement[] {
    return Array.from(document.querySelectorAll<HTMLElement>('#stream article'));
}

async function append_page(link: HTMLAnchorElement): Promise<void> {
    let url = link.href;
    url += url.indexOf('?') !== -1 ? '&' : '?';
    url += 'format=html-pure';
    const json = await get_json<StreamPage>(url);
    if (!json) {
        return;
    }
    hide_spinner();
    busy.delete(link);
    const before = stream_state.articles.length;
    stream_state.articles[before - 1]?.insertAdjacentHTML('afterend', json.stream);
    for (const next of stream_state.nav_next) {
        advance(next, json.next);
    }
    stream_state.articles = all_articles();
    const latest = stream_state.articles.slice(before);
    Lightbox.scan(latest);
    alter_html(latest);
    for (const article of latest) {
        render_maps(article);
        scaledown_images(article.querySelectorAll('img'));
    }
    if (latest[0]) {
        scroll_to_element(latest[0], 25);
    }
}

/**
 * "Next page": appends the next page's entries in place, until the page
 * holds `continuous_reading` entries; then follows the link.
 */
export function load_entries(target: HTMLElement): boolean {
    const link = target as HTMLAnchorElement;
    if (busy.has(link)) {
        return false;
    }
    busy.add(link);
    if (stream_state.articles.length >= stream_state.continuous_reading) {
        return follow_href(link);
    }
    show_spinner(link);
    void append_page(link);
    return false;
}
