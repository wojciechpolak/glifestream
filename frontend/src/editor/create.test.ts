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

import { type GlsEditor, create_editor } from './create';
import { saved_html } from './html';
import { extensions } from './schema';

let editor: Editor | undefined;

afterEach(() => {
    editor?.destroy();
    editor = undefined;
});

function new_editor(): Editor {
    const element = document.createElement('div');
    document.body.append(element);
    editor = new Editor({ element, extensions, injectCSS: false });
    return editor;
}

const PLAYER =
    '<div data-id="youtube-cjZvFY6__qw" class="play-video">' +
    '<a href="https://www.youtube.com/watch?v=cjZvFY6__qw" rel="nofollow">' +
    '<img src="https://i.ytimg.com/vi/cjZvFY6__qw/mqdefault.jpg" width="320" ' +
    'height="180" alt="YouTube Video"></a><div class="playbutton"></div></div>';

describe('pasting into the editor', () => {
    it('shows a pasted video address as the player the post will show', () => {
        const ed = new_editor();

        ed.view.pasteText('https://youtu.be/cjZvFY6__qw');

        expect(saved_html(ed.getHTML())).toBe(PLAYER);
        const view = ed.view.dom.querySelector('.editor-player');
        // The stream's own markup, which the theme draws as in the stream.
        expect(view?.querySelector('.play-video > img + .playbutton')).not.toBeNull();
        expect(view?.querySelector('img')?.getAttribute('src')).toBe(
            'https://i.ytimg.com/vi/cjZvFY6__qw/mqdefault.jpg',
        );
        expect(view?.textContent).toContain(
            'https://www.youtube.com/watch?v=cjZvFY6__qw',
        );
    });

    it('keeps any other address, or one within text, as text', () => {
        const ed = new_editor();

        ed.view.pasteText('see https://youtu.be/cjZvFY6__qw');
        ed.view.pasteText(' https://example.test/');

        expect(saved_html(ed.getHTML())).toBe(
            '<div>see https://youtu.be/cjZvFY6__qw https://example.test/</div>',
        );
    });
});

describe('the video button', () => {
    it('replaces the video of the selected player', () => {
        const ed = new_editor();
        ed.commands.setContent(PLAYER);
        ed.commands.setNodeSelection(0);

        expect(ed.commands.setPlayer('https://vimeo.com/42')).toBe(true);
        expect(ed.commands.setPlayer('https://example.test/42')).toBe(false);

        expect(saved_html(ed.getHTML())).toBe(
            '<div data-id="vimeo-42" class="play-video">' +
                '<a href="https://vimeo.com/42" rel="nofollow">' +
                '<img src="" width="320" height="180" alt="Vimeo Video"></a>' +
                '<div class="playbutton"></div></div>',
        );
        expect(ed.view.dom.querySelector('.editor-player-name')?.textContent).toBe(
            'Vimeo',
        );
    });
});

const CARD =
    '<div class="music-card"><span class="music-cover"><img src="/media/thumbs/1/1938.jpg" ' +
    'width="160" height="160" alt="Brave Men – Shoelace" /></span><p class="music-track">' +
    '<span class="music-title">Brave Men</span> <span class="music-artist">Shoelace</span>' +
    '</p><p class="music-links"><a href="https://open.spotify.com/search/x">Spotify</a></p></div>';

describe('the music card', () => {
    it('shows a post that is only its card as the card', () => {
        const element = document.createElement('div');
        document.body.append(element);
        const gls = create_editor(element, (msg) => msg);

        gls.load(CARD);

        expect(gls.is_empty()).toBe(false);
        expect(gls.music_card()).toEqual({
            artist: 'Shoelace',
            title: 'Brave Men',
            youtube: '',
            cover: '/media/thumbs/1/1938.jpg',
        });
        const view = element.querySelector('.editor-music-card .music-card');
        expect(view?.querySelector('.music-cover img')?.getAttribute('src')).toBe(
            '/media/thumbs/1/1938.jpg',
        );
        expect(view?.querySelector('.music-title')?.textContent).toBe('Brave Men');
        // Saved as the track it shows; the server adds the links.
        expect(gls.html()).toBe(
            '<div class="music-card"><span class="music-cover">' +
                '<img src="/media/thumbs/1/1938.jpg" width="160" height="160" alt="">' +
                '</span><p class="music-track"><span class="music-title">Brave Men</span> ' +
                '<span class="music-artist">Shoelace</span></p><p class="music-links"></p></div>',
        );
    });

    it('follows the fields: made, changed and taken away', () => {
        const element = document.createElement('div');
        document.body.append(element);
        const gls = create_editor(element, (msg) => msg);
        gls.load('<div>Loved it.</div>');

        gls.set_music_card({
            artist: 'Band',
            title: 'Song',
            youtube: 'https://youtu.be/abc',
            cover: '',
        });
        expect(gls.html()).toContain(
            '<div>Loved it.</div><div class="music-card"><div data-id="youtube-abc" ' +
                'class="play-video"><a href="https://www.youtube.com/watch?v=abc" ' +
                'rel="nofollow">YouTube</a>',
        );
        expect(
            element.querySelector('.music-card .play-video img')?.getAttribute('src'),
        ).toBe('https://i.ytimg.com/vi/abc/mqdefault.jpg');

        gls.set_music_card({ artist: 'Band', title: 'Song 2', youtube: '', cover: '' });
        expect(gls.music_card()?.title).toBe('Song 2');
        expect(element.querySelectorAll('.music-card')).toHaveLength(1);

        gls.set_music_card(null);
        expect(gls.music_card()).toBeNull();
        expect(gls.html()).toBe('<div>Loved it.</div>');
    });
});

/** An editor with its toolbar, and the toolbar's source button. */
function with_toolbar(): {
    gls: GlsEditor;
    element: HTMLElement;
    button: HTMLButtonElement;
} {
    const element = document.createElement('div');
    document.body.append(element);
    const gls = create_editor(element, (msg) => msg);
    const button = element.previousElementSibling?.querySelector(
        'button[title="HTML source"]',
    ) as HTMLButtonElement;
    return { gls, element, button };
}

describe('the HTML source', () => {
    it('shows the HTML the editor saves, a block a line, and locks the other buttons', () => {
        const { gls, element, button } = with_toolbar();
        gls.load('<div>One</div><div><b>Two</b></div>');

        button.click();

        const textarea = element.querySelector(
            'textarea.editor-source',
        ) as HTMLTextAreaElement;
        expect(element.classList.contains('source-mode')).toBe(true);
        expect(button.getAttribute('aria-pressed')).toBe('true');
        expect(textarea.value).toBe('<div>One</div>\n<div><strong>Two</strong></div>');
        const bold = element.previousElementSibling?.querySelector(
            'button[title="Bold"]',
        ) as HTMLButtonElement;
        expect(bold.disabled).toBe(true);
    });

    it('is what the post saves while it is open, as the editor reads it', () => {
        const { gls, element, button } = with_toolbar();
        const changes: number[] = [];
        gls.on_change(() => changes.push(1));
        gls.load('<div>One</div>');
        button.click();
        const textarea = element.querySelector(
            'textarea.editor-source',
        ) as HTMLTextAreaElement;

        textarea.value = '<div>Changed</div>\n<table><tr><td>cell</td></tr></table>';
        textarea.dispatchEvent(new Event('input'));

        expect(changes.length).toBeGreaterThan(0);
        // Markup the editor does not know goes, as it would once published.
        expect(gls.html()).toBe('<div>Changed</div><div>cell</div>');

        button.click();
        expect(element.classList.contains('source-mode')).toBe(false);
        expect(gls.html()).toBe('<div>Changed</div><div>cell</div>');
    });

    it('holds the music card the fields edit, and closes for another entry', () => {
        const { gls, element, button } = with_toolbar();
        gls.load('<div>Text</div>');
        button.click();

        gls.set_music_card({ artist: 'Band', title: 'Song', youtube: '', cover: '' });

        const textarea = element.querySelector(
            'textarea.editor-source',
        ) as HTMLTextAreaElement;
        expect(textarea.value).toContain('<span class="music-title">Song</span>');
        expect(gls.music_card()?.artist).toBe('Band');
        expect(element.classList.contains('source-mode')).toBe(true);

        gls.load('<div>Another</div>');
        expect(element.classList.contains('source-mode')).toBe(false);
        expect(gls.html()).toBe('<div>Another</div>');
    });
});
