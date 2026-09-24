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

import { describe, expect, it } from 'vitest';

import { is_html_empty, loadable_html, saved_html } from './html';

describe('is_html_empty', () => {
    it('is empty with only markup and whitespace', () => {
        expect(is_html_empty('<div><br></div>')).toBe(true);
        expect(is_html_empty('<div>  </div>\n<p></p>')).toBe(true);
        expect(is_html_empty('<div> &nbsp;&nbsp;</div>')).toBe(true);
    });

    it('is not empty with text', () => {
        expect(is_html_empty('<div>Hello</div>')).toBe(false);
    });

    it('is not empty with a picture or a player and no text', () => {
        expect(is_html_empty('<div><img src="a.png"></div>')).toBe(false);
        expect(is_html_empty('<iframe src="https://example.test/v"></iframe>')).toBe(
            false,
        );
    });
});

describe('saved_html', () => {
    it('keeps a run of spaces from collapsing', () => {
        expect(saved_html('<div>a b  c    d</div>')).toBe(
            '<div>a b &nbsp;c &nbsp;&nbsp;&nbsp;d</div>',
        );
    });

    it('leaves the spaces of code as they are', () => {
        expect(saved_html('<pre><code>a  b</code></pre>')).toBe(
            '<pre><code>a  b</code></pre>',
        );
    });

    it('writes a list item of one line without the line', () => {
        expect(
            saved_html('<ul><li><div>one</div></li><li><div>two</div></li></ul>'),
        ).toBe('<ul><li>one</li><li>two</li></ul>');
    });

    it('moves the alignment of a list line to its item', () => {
        expect(
            saved_html('<ol><li><div style="text-align: center">one</div></li></ol>'),
        ).toBe('<ol><li style="text-align: center">one</li></ol>');
    });

    it('keeps the lines of a list item of several', () => {
        const html = '<ul><li><div>one</div><div>two</div></li></ul>';

        expect(saved_html(html)).toBe(html);
    });

    it('drops the empty lines that end the text', () => {
        expect(saved_html('<ul><li><div>a</div></li></ul><div></div><div></div>')).toBe(
            '<ul><li>a</li></ul>',
        );
        expect(saved_html('<div></div>')).toBe('<div><br></div>');
    });

    it('writes an empty line as <div><br></div>', () => {
        expect(saved_html('<div>a</div><div></div><div>b</div>')).toBe(
            '<div>a</div><div><br></div><div>b</div>',
        );
    });
});

describe('loadable_html', () => {
    it('empties a line that only holds a <br>', () => {
        expect(loadable_html('<div>a</div><div><br></div><p><br></p>')).toBe(
            '<div>a</div><div></div><p></p>',
        );
    });

    it('keeps a <br> within a line', () => {
        const html = '<div>a<br>b</div>';

        expect(loadable_html(html)).toBe(html);
    });

    it('round-trips an empty line through saved_html', () => {
        const html = '<div>a</div><div><br></div><div>b</div>';

        expect(saved_html(loadable_html(html))).toBe(html);
    });
});
