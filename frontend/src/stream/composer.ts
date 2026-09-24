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

import type Quill from 'quill';

import type { SelfpostsClass } from '../api-types';
import { config } from '../config';
import { get_json, post_text } from '../http';
import {
    fade_in,
    hide,
    is_visible,
    show,
    slide_down,
    slide_up,
    stop,
    toggle,
} from '../ui/fx';
import { hide_spinner, show_spinner } from '../ui/spinner';
import { scroll_to_top } from '../util/scroll';
import { $M } from './entry-actions';
import { scaledown_images } from './images';
import { render_maps } from './maps';

/** The selfpost composer at the top of the stream. */
const composer = {
    /** The rich editor, when the page loaded Quill. */
    quill: undefined as Quill | undefined,
    /** The selfposts classes from api/gsc, once loaded. */
    gsc_load: false as false | SelfpostsClass[],
    /** Whether the class select has its options. */
    gsc_done: false,
    /** The entry being edited, or 0 for a new post. */
    editor_id: 0 as number | string,
};

function by_id(id: string): HTMLElement {
    return document.getElementById(id) as HTMLElement;
}

/** The plain textarea, which Quill replaces when the page loads it. */
function status_field(): HTMLTextAreaElement {
    return by_id('status') as HTMLTextAreaElement;
}

function fieldset(): HTMLElement | null {
    return document.querySelector<HTMLElement>('#share .fieldset');
}

function set_share_expanded(expanded: boolean): void {
    for (const form of document.querySelectorAll<HTMLElement>('#share > form')) {
        toggle(form, expanded);
    }
    document.getElementById('share')?.classList.toggle('share-collapsed', !expanded);
}

/** Opens or closes the composer. */
export function open_sharing(): boolean {
    composer.editor_id = 0;
    hide(by_id('update'));
    show(by_id('post'));
    const fs = fieldset();
    if (!fs) {
        return false;
    }
    const expanding = !is_visible(fs);
    set_share_expanded(expanding);
    stop(fs);
    if (expanding) {
        void slide_down(fs).then(function () {
            if (composer.quill) {
                composer.quill.focus();
            } else {
                status_field().focus();
            }
            if (!composer.gsc_done) {
                void get_selfposts_classes();
            }
        });
    } else {
        void slide_up(fs).then(function () {
            set_share_expanded(false);
        });
    }
    return false;
}

function show_selfposts_classes(): void {
    const sc = by_id('status-class') as HTMLSelectElement;
    const classes = composer.gsc_load as SelfpostsClass[];
    // oxlint-disable-next-line typescript/no-for-in-array -- iterates as the jQuery script did
    for (const i in classes) {
        const item = classes[i] as SelfpostsClass;
        sc.add(new Option(item['cls'], String(item['id'])));
    }
    composer.gsc_done = true;
}

async function get_selfposts_classes(): Promise<void> {
    if (!composer.gsc_load) {
        const json = await get_json<SelfpostsClass[]>(config.baseurl + 'api/gsc');
        if (!json) {
            return;
        }
        composer.gsc_load = json;
    }
    show_selfposts_classes();
}

export function open_more_sharing_options(link: HTMLElement): boolean {
    hide(link);
    void fade_in(by_id('more-sharing-options'));
    return false;
}

/**
 * The composer's HTML, as it is saved. Quill 2.0.3 writes every space as
 * &nbsp;, which would keep the text from wrapping, so a run of them goes
 * back to a space followed by what keeps the run from collapsing.
 */
export function editor_html(quill: Quill): string {
    return quill
        .getSemanticHTML()
        .replace(/(?:&nbsp;)+/g, (run) => ' ' + '&nbsp;'.repeat(run.length / 6 - 1));
}

/** Whether Quill's HTML holds neither text nor a picture. */
export function is_quill_empty(value: string): boolean {
    return (
        value
            .replace(/<(.|\n)*?>/g, '')
            .replaceAll('&nbsp;', ' ')
            .trim().length === 0 && value.indexOf('<img') === -1
    );
}

function checked(id: string): 1 | 0 {
    return (by_id(id) as HTMLInputElement).checked ? 1 : 0;
}

async function send(button: HTMLInputElement, content: string): Promise<void> {
    if (composer.editor_id) {
        const html = await post_text(config.baseurl + 'api/putcontent', {
            entry: composer.editor_id,
            content: content,
        });
        if (html !== null) {
            hide_spinner();
            button.disabled = false;
        }
        return;
    }
    const html = await post_text(config.baseurl + 'api/share', {
        sid: (by_id('status-class') as HTMLSelectElement).value,
        content: content,
        draft: checked('draft'),
        friends_only: checked('friends-only'),
    });
    if (html === null) {
        return;
    }
    hide_spinner();
    document
        .querySelector('#stream article.hentry')
        ?.insertAdjacentHTML('beforebegin', html);
    const first = document.querySelector('#stream article');
    render_maps(first);
    button.disabled = false;
    const fs = fieldset();
    if (fs) {
        void slide_up(fs).then(function () {
            set_share_expanded(false);
        });
    }
    editor_clear();
    if (first) {
        scaledown_images(first.querySelectorAll('img'));
    }
}

/** Posts the composer's content, or saves the entry being edited. */
export function share(target: HTMLElement): boolean {
    const docs = document.querySelector<HTMLInputElement>('input[name=docs]');
    if (docs && docs.files && docs.files.length) {
        return true;
    }
    const button = target as HTMLInputElement;
    button.disabled = true;
    let content: string;
    let isEmptyContent = false;
    if (composer.quill) {
        content = editor_html(composer.quill);
        isEmptyContent = is_quill_empty(content);
    } else {
        content = status_field().value;
        isEmptyContent = content.trim() === '';
    }
    if (isEmptyContent) {
        button.disabled = false;
        return false;
    }
    show_spinner(target);
    void send(button, content);
    return false;
}

function editor_clear(): void {
    if (composer.quill) {
        composer.quill.setContents([]);
    } else {
        status_field().value = '';
    }
}

/** Opens an entry's stored HTML in the composer for editing. */
export function edit_entry(control: HTMLElement, e?: Event): void {
    if (e) {
        e.preventDefault();
    }
    by_id('status-editor').style.height = '400px';
    set_share_expanded(true);
    for (const form of document.querySelectorAll<HTMLElement>('#share > form')) {
        show(form);
    }
    const fs = fieldset();
    if (fs) {
        show(fs);
    }
    if (!composer.gsc_done) {
        void get_selfposts_classes();
    }

    const id = control.id.split('-')[1] as string;
    show_spinner($M(control));
    void post_text(config.baseurl + 'api/getcontent', { entry: id, raw: 1 }).then(
        (html) => {
            if (html === null) {
                return;
            }
            hide_spinner();
            composer.editor_id = id;
            (composer.quill as Quill).clipboard.dangerouslyPasteHTML(html);
            toggle(by_id('update'));
            toggle(by_id('post'));
            scroll_to_top();
        },
    );
}

/** Replaces the plain textarea with Quill, when the page loaded it. */
export function init_quill(): void {
    const Editor = window.Quill;
    if (Editor) {
        hide(status_field());
        // Lines are <div>s, as in the entries the editor has always written.
        const Block = Editor.import('blots/block') as { tagName: string };
        Block.tagName = 'DIV';
        Editor.register('blots/block', Block, true);
        composer.quill = new Editor('#status-editor', {
            modules: {
                toolbar: {
                    container: [
                        [{ font: [] }, { size: [] }],
                        ['bold', 'italic', 'underline', 'strike'],
                        [{ color: [] }, { background: [] }],
                        [{ header: '1' }, { header: '2' }, 'blockquote', 'code-block'],
                        [
                            { list: 'ordered' },
                            { list: 'bullet' },
                            { indent: '-1' },
                            { indent: '+1' },
                        ],
                        ['direction', { align: [] }],
                        ['link', 'image', 'video'],
                        ['clean'],
                    ],
                },
            },
            theme: 'snow',
        });
    }
}

/** The PWA share target: /share?title=&text=&url= opens a filled composer. */
export function init_share_target(): void {
    const parsedUrl = new URL(window.location.href);
    if (parsedUrl.pathname.endsWith('/share')) {
        open_sharing();
        const title = parsedUrl.searchParams.get('title');
        const text = parsedUrl.searchParams.get('text');
        const url = parsedUrl.searchParams.get('url');
        let body = '';
        if (title) {
            body += title + '<br>';
        }
        if (text) {
            body += text + '<br>';
        }
        if (url) {
            body += url + '<br>';
        }
        if (composer.quill) {
            composer.quill.clipboard.dangerouslyPasteHTML(body);
        } else {
            status_field().value = body.replace(/<br>/g, '\n');
        }
    }
}
