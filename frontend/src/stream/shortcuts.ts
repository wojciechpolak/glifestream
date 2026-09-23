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

import { scroll_to_element } from '../util/scroll';
import { composer, open_sharing } from './composer';
import { favorite_entry, hide_entry, unhide_entry } from './entry-actions';
import { stream_state } from './state';

/**
 * Keyboard shortcuts of the stream: j and k move between entries, f
 * favorites, h hides or brings back, and a opens the composer.
 */
export function kshortcuts(e?: KeyboardEvent): true | void {
    if (composer.quill && composer.quill.hasFocus()) {
        return;
    }
    let code: number | undefined;
    let ent: HTMLElement | undefined;
    if (!e) {
        e = window.event as KeyboardEvent;
    }
    if (e.keyCode) {
        code = e.keyCode;
    } else if (e.which) {
        code = e.which;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) {
        return true;
    }

    const articles = stream_state.articles;
    switch (code) {
        case 97:
            /* a */
            open_sharing();
            break;
        case 106:
            /* j */
            if (stream_state.current_article + 1 === articles.length) {
                stream_state.nav_next.trigger('click');
            } else {
                highlight_article(
                    articles[++stream_state.current_article] as HTMLElement,
                );
            }
            break;
        case 107:
            /* k */
            if (stream_state.current_article - 1 < 0) {
                const prev = $('#stream a.prev');
                if (prev.length) {
                    window.location.href = prev.attr('href') as string;
                }
            } else {
                highlight_article(
                    articles[--stream_state.current_article] as HTMLElement,
                );
            }
            break;
        case 102:
            /* f */
            ent = articles[stream_state.current_article];
            if (ent) {
                const c = $('span.favorite-control', ent);
                if (c.length) {
                    favorite_entry.call(c[0] as HTMLElement);
                }
            }
            break;
        case 104:
            /* h */
            ent = articles[stream_state.current_article];
            if (ent) {
                const id = ent.id.split('-')[1] as string;
                let c = $('#hidden-' + id + ' a');
                if (c.length) {
                    unhide_entry.call(c[0] as HTMLElement);
                } else {
                    c = $('span.hide-control', ent);
                    if (c.length) {
                        hide_entry.call(c[0] as HTMLElement);
                    }
                }
            }
            break;
    }
}

function highlight_article(article: HTMLElement): void {
    $('a:first', article).focus().blur();
    stream_state.articles.removeClass('entry-highlight');
    $(article).addClass('entry-highlight');
    scroll_to_element(article, 24);
}
