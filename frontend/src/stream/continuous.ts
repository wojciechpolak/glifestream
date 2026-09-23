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
import { Graybox } from '../ui/graybox';
import { hide_spinner, show_spinner } from '../ui/spinner';
import { follow_href } from '../util/navigation';
import { scroll_to_element } from '../util/scroll';
import { scaledown_images } from './images';
import { render_map } from './maps';
import { alter_html } from './media';
import { stream_state } from './state';

type NextLink = HTMLAnchorElement & { busy?: boolean };

/**
 * "Next page": appends the next page's entries in place, until the page
 * holds `continuous_reading` entries; then follows the link.
 */
export function load_entries(this: HTMLAnchorElement): boolean {
    const that = this as NextLink;
    if (that.busy) {
        return false;
    }
    that.busy = true;
    if (stream_state.articles.length >= stream_state.continuous_reading) {
        return follow_href.call(this);
    }
    show_spinner(this);
    let url = this.href;
    url += url.indexOf('?') !== -1 ? '&' : '?';
    url += 'format=html-pure';
    $.getJSON(url, function (json: StreamPage) {
        hide_spinner();
        that.busy = false;
        let num = stream_state.articles.length;
        $(stream_state.articles[num - 1] as HTMLElement).after(json.stream);
        stream_state.nav_next.each(function () {
            let s = this.href.indexOf('start=');
            if (s !== -1 && json.next) {
                this.href = this.href.substring(0, s + 6) + json.next;
            } else {
                s = this.href.indexOf('page=');
                if (s !== -1 && json.next) {
                    this.href = this.href.substring(0, s + 5) + json.next;
                } else {
                    $(this).remove();
                }
            }
        });
        stream_state.articles = $('#stream article');
        num = stream_state.articles.length - num;
        const latest = $('#stream article').slice(-num);
        Graybox.scan(latest);
        alter_html(latest);
        $('a.map', latest).each(render_map);
        scaledown_images($('img', latest));
        scroll_to_element(latest[0] as HTMLElement, 25);
    });
    return false;
}
