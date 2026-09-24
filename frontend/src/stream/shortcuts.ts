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
import { open_sharing } from './composer';
import { favorite_entry, hide_entry, unhide_entry } from './entry-actions';
import { stream_state } from './state';

const EDITABLE =
    'input, textarea, select, [contenteditable=""], [contenteditable="true"]';

/** Whether the key goes to a field the reader types in, such as the composer. */
function typed_in_field(e: KeyboardEvent): boolean {
    const target = e.target;
    return (
        target instanceof HTMLElement &&
        (target.isContentEditable || target.closest(EDITABLE) !== null)
    );
}

/**
 * Keyboard shortcuts of the stream: j and k move between entries, f
 * favorites, h hides or brings back, and a opens the composer.
 */
export function kshortcuts(e: KeyboardEvent): void {
    if (typed_in_field(e) || e.ctrlKey || e.metaKey || e.altKey) {
        return;
    }

    const articles = stream_state.articles;
    let ent: HTMLElement | undefined;
    switch (e.key) {
        case 'a':
            open_sharing();
            break;
        case 'j':
            if (stream_state.current_article + 1 === articles.length) {
                for (const link of stream_state.nav_next) {
                    link.click();
                }
            } else {
                highlight_article(
                    articles[++stream_state.current_article] as HTMLElement,
                );
            }
            break;
        case 'k':
            if (stream_state.current_article - 1 < 0) {
                const prev = document.querySelector('#stream a.prev');
                if (prev) {
                    window.location.href = prev.getAttribute('href') as string;
                }
            } else {
                highlight_article(
                    articles[--stream_state.current_article] as HTMLElement,
                );
            }
            break;
        case 'f':
            ent = articles[stream_state.current_article];
            if (ent) {
                const c = ent.querySelector<HTMLElement>('span.favorite-control');
                if (c) {
                    favorite_entry(c);
                }
            }
            break;
        case 'h':
            ent = articles[stream_state.current_article];
            if (ent) {
                const id = ent.id.split('-')[1] as string;
                const undo = document.querySelector<HTMLElement>(
                    '#hidden-' + id + ' a',
                );
                const hide = ent.querySelector<HTMLElement>('span.hide-control');
                if (undo) {
                    unhide_entry(undo);
                } else if (hide) {
                    hide_entry(hide);
                }
            }
            break;
        default:
            return;
    }
    // The key moved focus or the page; it must not also type there.
    e.preventDefault();
}

/** Listens for the shortcuts; a key typed in a field is left to the field. */
export function init_shortcuts(): void {
    document.addEventListener('keypress', kshortcuts);
}

function highlight_article(article: HTMLElement): void {
    const first = article.querySelector('a');
    first?.focus();
    first?.blur();
    for (const a of stream_state.articles) {
        a.classList.remove('entry-highlight');
    }
    article.classList.add('entry-highlight');
    scroll_to_element(article, 24);
}
