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

import { Editor } from '@tiptap/core';
import { afterEach, describe, expect, it } from 'vitest';

import { saved_html } from './html';
import { extensions } from './schema';

let editor: Editor | undefined;

afterEach(() => {
    editor?.destroy();
    editor = undefined;
});

describe('pasting into the editor', () => {
    it('keeps a pasted address as text, for the server to expand', () => {
        const element = document.createElement('div');
        document.body.append(element);
        editor = new Editor({ element, extensions, injectCSS: false });

        editor.view.pasteText('https://www.youtube.com/watch?v=cjZvFY6__qw');

        expect(saved_html(editor.getHTML())).toBe(
            '<div>https://www.youtube.com/watch?v=cjZvFY6__qw</div>',
        );
    });
});
