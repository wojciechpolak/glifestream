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

import type { EditContent, SelfpostsClass } from '../api-types';
import { config } from '../config';
import type { GlsEditor, MusicTrack } from '../editor/create';
import { get_json, post_json, post_text } from '../http';
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
import { h } from '../util/dom';
import { _ } from '../util/i18n';
import { scroll_to_top } from '../util/scroll';
import { $M } from './entry-actions';
import { scaledown_images } from './images';
import { render_maps } from './maps';
import { clear_preview, refresh_preview, schedule_preview } from './preview';

/** The selfpost composer at the top of the stream. */
const composer = {
    /** The rich editor, when the page loaded it. */
    editor: undefined as GlsEditor | undefined,
    /** The selfposts classes from api/gsc, once loaded. */
    gsc_load: false as false | SelfpostsClass[],
    /** Whether the class select has its options. */
    gsc_done: false,
    /** The entry being edited, or 0 for a new post. */
    editor_id: 0 as number | string,
    /** Whether the entry being edited is a post, whose class may change. */
    editor_post: false,
    /** Whether the music fields are writing to the editor's card. */
    syncing: false,
};

function by_id(id: string): HTMLElement {
    return document.getElementById(id) as HTMLElement;
}

/** The plain textarea, which the rich editor replaces when the page loads it. */
function status_field(): HTMLTextAreaElement {
    return by_id('status') as HTMLTextAreaElement;
}

function class_select(): HTMLSelectElement | null {
    return document.getElementById('status-class') as HTMLSelectElement | null;
}

/**
 * Locks the class of an entry that is no post, saying why on hover. The
 * option that only named its class goes once the lock does.
 */
function lock_class(select: HTMLSelectElement, locked: boolean): void {
    select.disabled = locked;
    select.title = locked ? _('An imported entry keeps the class of its service.') : '';
    if (!locked) {
        for (const option of select.querySelectorAll('option[data-entry-class]')) {
            option.remove();
        }
    }
}

/**
 * Shows the class `cls` of the entry being edited. Only a post's may
 * change; another entry's is locked, shown also when no post has it.
 */
function select_class(cls: string, post: boolean): void {
    const select = class_select();
    if (!select) {
        return;
    }
    lock_class(select, false);
    let option = [...select.options].find((o) => o.text === cls);
    if (!option && !post) {
        option = new Option(cls, '');
        option.dataset['entryClass'] = '';
        select.add(option);
    }
    if (option) {
        select.value = option.value;
    }
    lock_class(select, !post);
}

/** Ticks the draft and friends-only checkboxes, showing them when ticked. */
function set_flags(draft: boolean, friends_only: boolean): void {
    for (const [id, value] of [
        ['draft', draft],
        ['friends-only', friends_only],
    ] as const) {
        const box = document.getElementById(id) as HTMLInputElement | null;
        if (box) {
            box.checked = value;
        }
    }
    const more = document.getElementById('expand-sharing');
    if ((draft || friends_only) && more && is_visible(more)) {
        open_more_sharing_options(more);
    }
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
    if (composer.editor_id) {
        // A new post starts without the checkboxes of the entry edited.
        set_flags(false, false);
    }
    composer.editor_id = 0;
    composer.editor_post = false;
    const select = class_select();
    if (select) {
        lock_class(select, false);
    }
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
            if (composer.editor) {
                composer.editor.focus();
            } else {
                status_field().focus();
            }
            if (!composer.gsc_done) {
                void get_selfposts_classes();
            }
        });
        update_preview();
    } else {
        clear_preview();
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

/** The fields of a music card, as the share form names them after music_. */
const MUSIC_FIELDS = ['artist', 'title', 'youtube', 'cover'];

function music_field(name: string): HTMLInputElement | null {
    return document.getElementById('music-' + name) as HTMLInputElement | null;
}

function music_value(name: string): string {
    return music_field(name)?.value.trim() ?? '';
}

/**
 * The music card fields that are filled in, as share parameters. Only the
 * plain composer sends them: the rich editor holds the card itself.
 */
function music_params(): Record<string, string> {
    const params: Record<string, string> = {};
    if (composer.editor) {
        return params;
    }
    for (const name of MUSIC_FIELDS) {
        const value = music_field(name)?.value.trim();
        if (value) {
            params['music_' + name] = value;
        }
    }
    return params;
}

/** Fills the music card fields, and opens them when there is a card. */
function fill_music(track: MusicTrack | null): void {
    for (const name of MUSIC_FIELDS) {
        const input = music_field(name);
        const value = track ? track[name as keyof MusicTrack] : '';
        // Left alone when it says the same, to keep the caret of the writer.
        if (input && input.value !== value) {
            input.value = value;
        }
    }
    document.getElementById('music-track')?.toggleAttribute('open', !!track);
    // The fields are among the more options, which a card opens.
    const more = document.getElementById('expand-sharing');
    if (track && more && is_visible(more)) {
        open_more_sharing_options(more);
    }
}

/** The editor's card follows its fields: made once they name the track. */
function card_from_fields(): void {
    if (!composer.editor) {
        return;
    }
    const track: MusicTrack = {
        artist: music_value('artist'),
        title: music_value('title'),
        youtube: music_value('youtube'),
        cover: music_value('cover'),
    };
    composer.syncing = true;
    composer.editor.set_music_card(track.artist || track.title ? track : null);
    composer.syncing = false;
}

/** The fields follow the editor's card, which the writer may also remove. */
function fields_from_card(): void {
    if (composer.editor && !composer.syncing) {
        fill_music(composer.editor.music_card());
    }
}

/** Whether the composer describes a track, which makes a post of its own. */
function has_music(): boolean {
    const params = music_params();
    return !!(params['music_artist'] && params['music_title']);
}

/** What the composer holds: its content and whether that is empty. */
function composer_content(): { content: string; empty: boolean } {
    if (composer.editor) {
        return { content: composer.editor.html(), empty: composer.editor.is_empty() };
    }
    const content = status_field().value;
    return { content, empty: content.trim() === '' };
}

/** What saving the edited entry sends: its HTML and, for a post, its class. */
function edit_params(content: string): Record<string, string | number> {
    const params: Record<string, string | number> = {
        entry: composer.editor_id,
        content,
    };
    if (composer.editor_post) {
        params['sid'] = class_select()?.value ?? '';
    }
    params['draft'] = checked('draft');
    params['friends_only'] = checked('friends-only');
    return params;
}

/** The request for the preview of what the composer holds, or null. */
function preview_params(): Record<string, string | number> | null {
    const { content, empty } = composer_content();
    if (empty && !has_music()) {
        return null;
    }
    if (composer.editor_id) {
        return edit_params(content);
    }
    const sid = class_select()?.value;
    return {
        content,
        ...(sid ? { sid } : {}),
        draft: checked('draft'),
        friends_only: checked('friends-only'),
        ...music_params(),
    };
}

/** Lets the preview follow the composer. */
function update_preview(): void {
    schedule_preview(preview_params);
}

function checked(id: string): 1 | 0 {
    return (by_id(id) as HTMLInputElement).checked ? 1 : 0;
}

async function send(button: HTMLInputElement, content: string): Promise<void> {
    if (composer.editor_id) {
        const html = await post_text(config.baseurl + 'api/putcontent', {
            ...edit_params(content),
            article: 1,
        });
        if (html !== null) {
            hide_spinner();
            button.disabled = false;
            // The entry as saved: its thumbnails, its card, the icon of its class.
            const article = document.getElementById('entry-' + composer.editor_id);
            if (article) {
                article.outerHTML = html.trim();
                const saved = document.getElementById('entry-' + composer.editor_id);
                render_maps(saved);
                if (saved) {
                    scaledown_images(saved.querySelectorAll('img'));
                }
            }
        }
        return;
    }
    const html = await post_text(config.baseurl + 'api/share', {
        sid: (by_id('status-class') as HTMLSelectElement).value,
        content: content,
        draft: checked('draft'),
        friends_only: checked('friends-only'),
        ...music_params(),
    });
    if (html === null) {
        return;
    }
    hide_spinner();
    // The post itself takes the place of its preview.
    clear_preview();
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
    const { content, empty } = composer_content();
    // A track alone is a post, also once it is edited.
    if (empty && !has_music()) {
        button.disabled = false;
        return false;
    }
    show_spinner(target);
    void send(button, content);
    return false;
}

function editor_clear(): void {
    clear_preview();
    if (composer.editor) {
        composer.editor.clear();
    } else {
        status_field().value = '';
    }
    fill_music(null);
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
    const classes = composer.gsc_done ? Promise.resolve() : get_selfposts_classes();

    const id = control.id.split('-')[1] as string;
    show_spinner($M(control));
    void Promise.all([
        post_json<EditContent>(config.baseurl + 'api/editcontent', { entry: id }),
        classes,
    ]).then(([data]) => {
        if (data === null) {
            return;
        }
        hide_spinner();
        composer.editor_id = id;
        composer.editor_post = data.post;
        if (composer.editor) {
            composer.editor.load(data.content);
        } else {
            status_field().value = data.content;
        }
        select_class(data.cls, data.post);
        set_flags(data.draft, data.friends_only);
        fill_music(composer.editor ? composer.editor.music_card() : null);
        void refresh_preview(preview_params());
        toggle(by_id('update'));
        toggle(by_id('post'));
        scroll_to_top();
    });
}

/** Replaces the plain textarea with the rich editor, when the page loaded it. */
export function init_editor(): void {
    const create = window.create_gls_editor;
    if (create) {
        hide(status_field());
        composer.editor = create(by_id('status-editor'), _);
        composer.editor.on_change(() => {
            fields_from_card();
            update_preview();
        });
    } else {
        // Not on a page without the composer.
        document.getElementById('status')?.addEventListener('input', update_preview);
    }
    // Whatever else changes the post: its flags, its class and its music
    // card, which the editor shows as it will be.
    for (const id of ['draft', 'friends-only']) {
        document.getElementById(id)?.addEventListener('change', update_preview);
    }
    for (const id of ['status-class', ...MUSIC_FIELDS.map((name) => 'music-' + name)]) {
        for (const type of ['input', 'change']) {
            document.getElementById(id)?.addEventListener(type, () => {
                card_from_fields();
                update_preview();
            });
        }
    }
}

/** The PWA share target: /share?title=&text=&url= opens a filled composer. */
export function init_share_target(): void {
    const parsedUrl = new URL(window.location.href);
    if (parsedUrl.pathname.endsWith('/share')) {
        open_sharing();
        const lines = ['title', 'text', 'url']
            .map((name) => parsedUrl.searchParams.get(name))
            .filter((line) => !!line) as string[];
        if (composer.editor) {
            const body = h(
                'div',
                null,
                lines.map((line) => h('div', null, [line])),
            );
            composer.editor.load(body.innerHTML);
        } else {
            status_field().value = lines.map((line) => line + '\n').join('');
        }
    }
}
