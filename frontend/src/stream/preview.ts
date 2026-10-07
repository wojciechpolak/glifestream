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

// The live preview of a post: the article the stream will show, made by
// the server from what the composer holds (api/preview) and shown under the
// composer, where the post will appear.

import { config } from '../config';
import { type Params, try_post_text } from '../http';
import { h } from '../util/dom';
import { _ } from '../util/i18n';
import { scaledown_images } from './images';
import { render_maps } from './maps';

/** How long the composer stays unchanged before the preview follows it. */
export const PREVIEW_DELAY_MS = 700;

const state = {
    timer: 0,
    /** The number of the latest request; an older answer is dropped. */
    seq: 0,
};

/** The preview shown now, if any. */
export function preview_article(): HTMLElement | null {
    return document.querySelector<HTMLElement>('#stream > article.entry-preview');
}

function show(html: string): void {
    const template = document.createElement('template');
    template.innerHTML = html.trim();
    const article = template.content.querySelector('article');
    if (!article) {
        remove_preview();
        return;
    }
    article.classList.add('entry-preview');
    article.setAttribute('aria-label', _('Preview'));
    // Last: the theme lays out the article by its first child, the icon.
    article.append(h('span', { className: 'entry-preview-label' }, [_('Preview')]));
    const old = preview_article();
    if (old) {
        old.replaceWith(article);
    } else {
        document.getElementById('share')?.after(article);
    }
    render_maps(article);
    scaledown_images(article.querySelectorAll('img'));
}

function remove_preview(): void {
    preview_article()?.remove();
}

/**
 * Shows the article `params` make: what the composer would post or save.
 * No params, for a composer with nothing in it, removes the preview.
 */
export async function refresh_preview(params: Params | null): Promise<void> {
    window.clearTimeout(state.timer);
    const seq = ++state.seq;
    if (!params) {
        remove_preview();
        return;
    }
    const html = await try_post_text(config.baseurl + 'api/preview', params);
    if (seq !== state.seq) {
        return;
    }
    if (html) {
        show(html);
    } else {
        remove_preview();
    }
}

/** Refreshes the preview once the composer has been still for a moment. */
export function schedule_preview(params: () => Params | null): void {
    window.clearTimeout(state.timer);
    state.timer = window.setTimeout(() => {
        void refresh_preview(params());
    }, PREVIEW_DELAY_MS);
}

/** Removes the preview, and drops the answer to a request on its way. */
export function clear_preview(): void {
    window.clearTimeout(state.timer);
    state.seq++;
    remove_preview();
}
