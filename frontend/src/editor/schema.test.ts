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

import { generateHTML, getSchema } from '@tiptap/core';
import { DOMParser } from '@tiptap/pm/model';
import { describe, expect, it } from 'vitest';

import { loadable_html, saved_html } from './html';
import { extensions } from './schema';

const parser = DOMParser.fromSchema(getSchema(extensions));

/**
 * What the editor saves after it reads `html` and nobody changes it. The
 * HTML is parsed in a <template>, where happy-dom, unlike a browser's
 * DOMParser, loads no player.
 */
function round_trip(html: string): string {
    const template = document.createElement('template');
    template.innerHTML = loadable_html(html);
    const doc = parser.parse(template.content);
    return saved_html(generateHTML(doc.toJSON(), extensions));
}

describe('the editor schema', () => {
    it('writes lines as <div>s and reads <p>s as lines', () => {
        expect(round_trip('<div>one</div><p>two</p>')).toBe(
            '<div>one</div><div>two</div>',
        );
    });

    it('keeps the empty lines Quill wrote', () => {
        expect(round_trip('<div>a</div><div><br></div><div>b</div>')).toBe(
            '<div>a</div><div><br></div><div>b</div>',
        );
    });

    it("reads Quill's alignment classes as alignment", () => {
        expect(
            round_trip(
                '<div class="ql-align-center">mid</div><h1 class="ql-align-right">T</h1>',
            ),
        ).toBe(
            '<div style="text-align: center;">mid</div><h1 style="text-align: right;">T</h1>',
        );
    });

    it('keeps the lists and marks Quill wrote', () => {
        const html =
            '<ul><li>one</li><li><strong>two</strong></li></ul>' +
            '<ol><li><em>three</em> <u>four</u> <s>five</s></li></ol>';

        expect(round_trip(html)).toBe(html);
    });

    it("keeps Quill's videos and pictures", () => {
        expect(
            round_trip(
                '<iframe class="ql-video" frameborder="0" allowfullscreen="true" ' +
                    'src="https://www.youtube.com/embed/abc"></iframe>' +
                    '<div><img src="data:image/png;base64,AAAA"></div>',
            ),
        ).toBe(
            '<iframe frameborder="0" allowfullscreen="true" ' +
                'src="https://www.youtube.com/embed/abc"></iframe>' +
                '<div><img src="data:image/png;base64,AAAA"></div>',
        );
    });

    it('drops a player that is not on the web', () => {
        expect(
            round_trip('<iframe src="javascript:alert(1)"></iframe><div>a</div>'),
        ).toBe('<div>a</div>');
    });

    it('keeps the text of formatting it drops', () => {
        expect(
            round_trip(
                '<div><span class="ql-size-large ql-font-serif">big</span></div>',
            ),
        ).toBe('<div>big</div>');
    });
});
