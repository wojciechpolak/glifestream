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

// The composer's rich editor: Tiptap, with the toolbar above it. The page
// script only sees GlsEditor, so it carries none of Tiptap itself.

import { Editor, generateHTML, generateJSON } from '@tiptap/core';

import { is_html_empty, loadable_html, saved_html, source_html } from './html';
import { type MusicTrack, extensions, music_card_of } from './schema';

export type { MusicTrack } from './schema';
import { build_toolbar } from './toolbar';

/** What the composer does with its rich editor. */
export interface GlsEditor {
    focus(): void;
    /** The content, as it is saved. */
    html(): string;
    /** Whether the content holds neither text, a picture nor a player. */
    is_empty(): boolean;
    /** Replaces the content with an entry's HTML. */
    load(html: string): void;
    /** Calls `listener` after each change the writer makes. */
    on_change(listener: () => void): void;
    /** The track of the post's music card, or null. */
    music_card(): MusicTrack | null;
    /** Shows `track` in the post's music card; null takes it away. */
    set_music_card(track: MusicTrack | null): void;
    clear(): void;
}

/**
 * The HTML source of the editor: the HTML it saves, to read and change in a
 * textarea. It has no saving of its own. What it holds is what the editor
 * reads of it, so markup the editor does not know goes; publishing the post
 * saves it, and the editor shows it again when the source is closed.
 */
class Source {
    readonly textarea: HTMLTextAreaElement;
    readonly button: HTMLButtonElement;
    open = false;
    private readonly editor: Editor;
    private readonly element: HTMLElement;
    private readonly toolbar: HTMLElement;

    constructor(
        editor: Editor,
        element: HTMLElement,
        toolbar: HTMLElement,
        gettext: (msg: string) => string,
    ) {
        this.editor = editor;
        this.element = element;
        this.toolbar = toolbar;
        this.textarea = document.createElement('textarea');
        this.textarea.className = 'editor-source';
        this.textarea.spellcheck = false;
        element.append(this.textarea);

        this.button = document.createElement('button');
        this.button.type = 'button';
        this.button.title = gettext('HTML source');
        this.button.setAttribute('aria-label', this.button.title);
        this.button.setAttribute('aria-pressed', 'false');
        const icon = document.createElement('i');
        icon.className = 'fa-solid fa-file-code';
        icon.setAttribute('aria-hidden', 'true');
        this.button.append(icon);
        this.button.addEventListener('mousedown', (event) => event.preventDefault());
        this.button.addEventListener('click', () => {
            if (this.open) {
                this.close();
            } else {
                this.show();
            }
        });
        const group = document.createElement('span');
        group.className = 'editor-toolbar-group';
        group.append(this.button);
        toolbar.append(group);
    }

    /** The document the source holds, as the editor reads it. */
    json(): ReturnType<typeof generateJSON> {
        return generateJSON(loadable_html(this.textarea.value), extensions);
    }

    /** The HTML the source holds, as the editor would save it. */
    html(): string {
        return saved_html(generateHTML(this.json(), extensions));
    }

    /** Puts the source into the editor, which saves what it reads of it. */
    apply(): void {
        this.editor.commands.setContent(loadable_html(this.textarea.value));
    }

    show(): void {
        this.textarea.value = source_html(saved_html(this.editor.getHTML()));
        this.set_open(true);
        this.textarea.focus();
    }

    /** Closes the source, the editor showing what it holds. */
    close(): void {
        if (this.open) {
            this.set_open(false);
            this.apply();
        }
    }

    private set_open(open: boolean): void {
        this.open = open;
        this.element.classList.toggle('source-mode', open);
        this.button.setAttribute('aria-pressed', String(open));
        // The formatting buttons act on the editor, which the source hides.
        for (const other of this.toolbar.querySelectorAll('button')) {
            if (other !== this.button) {
                other.disabled = open;
            }
        }
    }
}

/** Makes `element` the editor, with its toolbar just before it. */
export function create_editor(
    element: HTMLElement,
    gettext: (msg: string) => string,
): GlsEditor {
    const editor = new Editor({
        element,
        extensions,
        // Its stylesheet comes with this bundle's (editor.css).
        injectCSS: false,
    });
    const toolbar = build_toolbar(editor, gettext);
    element.before(toolbar);
    const source = new Source(editor, element, toolbar, gettext);
    const html = (): string =>
        source.open ? source.html() : saved_html(editor.getHTML());
    return {
        focus: () => {
            if (source.open) {
                source.textarea.focus();
            } else {
                editor.commands.focus();
            }
        },
        html,
        is_empty: () => is_html_empty(html()),
        load: (content) => {
            source.close();
            editor.commands.setContent(loadable_html(content));
        },
        music_card: () =>
            music_card_of(
                source.open
                    ? editor.schema.nodeFromJSON(source.json())
                    : editor.state.doc,
            ),
        set_music_card: (track) => {
            if (source.open) {
                // Through the editor, and back into the source, still open.
                source.apply();
                editor.commands.setMusicCard(track);
                source.textarea.value = source_html(saved_html(editor.getHTML()));
            } else {
                editor.commands.setMusicCard(track);
            }
        },
        on_change: (listener) => {
            editor.on('update', listener);
            source.textarea.addEventListener('input', listener);
        },
        clear: () => {
            source.close();
            editor.commands.clearContent();
        },
    };
}
