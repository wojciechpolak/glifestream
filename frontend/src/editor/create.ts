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

import { Editor } from '@tiptap/core';

import { is_html_empty, loadable_html, saved_html } from './html';
import { extensions } from './schema';
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
    clear(): void;
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
    element.before(build_toolbar(editor, gettext));
    const html = (): string => saved_html(editor.getHTML());
    return {
        focus: () => {
            editor.commands.focus();
        },
        html,
        is_empty: () => is_html_empty(html()),
        load: (content) => {
            editor.commands.setContent(loadable_html(content));
        },
        clear: () => {
            editor.commands.clearContent();
        },
    };
}
