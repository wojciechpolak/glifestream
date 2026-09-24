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

import { afterEach, describe, expect, it, vi } from 'vitest';

import { alter_html, play_audio, toggle_video } from './media';

afterEach(() => {
    vi.restoreAllMocks();
    delete window.user_alter_html;
    document.body.innerHTML = '';
});

function stream(html: string): HTMLElement {
    document.body.innerHTML = '<section id="stream">' + html + '</section>';
    return document.getElementById('stream') as HTMLElement;
}

function click(): MouseEvent {
    return new MouseEvent('click', { button: 0 });
}

describe('alter_html', () => {
    it('turns video links into play-video blocks', () => {
        const root = stream(`
            <div class="thumbnails">
              <a href="https://www.youtube.com/watch?v=abc"><img></a>
              <a href="https://vimeo.com/42"><img></a>
              <a href="https://example.com/photo.jpg"><img></a>
            </div>`);

        alter_html(root);

        const blocks = root.querySelectorAll('.play-video');
        expect(Array.from(blocks, (b) => b.id)).toEqual(['youtube-abc', 'vimeo-42']);
        const youtube = blocks[0] as HTMLElement;
        expect(youtube.firstElementChild?.tagName).toBe('A');
        expect(youtube.lastElementChild?.className).toBe('playbutton');
    });

    it('turns audio files into play-audio links', () => {
        const root = stream(`
            <div class="files"><a href="/a.mp3">a</a> <a href="/b.ogg">b</a>
            <a href="/c.pdf">c</a></div>`);

        alter_html(root);

        const spans = root.querySelectorAll<HTMLElement>('span.play-audio');
        expect(spans).toHaveLength(2);
        expect(spans[0]?.dataset['id']).toBe('audio-x');
        expect(spans[1]?.querySelector('a')?.getAttribute('href')).toBe('/b.ogg');
    });

    it('hands the same batch to user_alter_html', () => {
        const root = stream(
            '<article id="entry-1"></article><article id="entry-2"></article>',
        );
        const batch = Array.from(root.querySelectorAll<HTMLElement>('article'));
        const user = vi.fn();
        window.user_alter_html = user;

        alter_html(batch);

        expect(user).toHaveBeenCalledWith(batch);
    });
});

describe('play_audio', () => {
    it('opens a player for the file, and closes it on the next click', () => {
        const root = stream(
            '<p><span class="play-audio" data-id="audio-x"><a href="/a.mp3">a</a></span></p>',
        );
        const span = root.querySelector('span') as HTMLElement;
        vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();

        expect(play_audio(span, click())).toBe(false);
        const audio = root.querySelector('.player.audio audio') as HTMLAudioElement;
        expect(audio.getAttribute('src')).toBe('/a.mp3');
        expect(audio.controls).toBe(true);

        play_audio(span, click());
        expect(root.querySelector('.player')).toBeNull();
    });

    it('follows the link of a provider it does not know', () => {
        const root = stream(
            '<span class="play-audio" data-id="other-1"><a href="#">a</a></span>',
        );

        expect(play_audio(root.querySelector('span') as HTMLElement, click())).toBe(
            true,
        );
    });
});

describe('toggle_video', () => {
    it('plays a provider template after the block, then stops it', () => {
        // Out of the document, so that happy-dom does not load the player.
        const root = document.createElement('section');
        root.innerHTML =
            '<div id="youtube-abc" class="play-video"><a href="#"></a><div class="playbutton"></div></div>';
        const block = root.querySelector('.play-video') as HTMLElement;

        expect(toggle_video(block)).toBe(false);
        const player = block.nextElementSibling as HTMLElement;
        expect(player.className).toBe('player video youtube');
        expect(player.querySelector('iframe')?.getAttribute('src')).toBe(
            'https://www.youtube.com/embed/abc?autoplay=1&rel=0',
        );
        expect(player.querySelector('iframe')?.getAttribute('referrerpolicy')).toBe(
            'strict-origin-when-cross-origin',
        );
        expect(block.querySelector('.stopbutton')).not.toBeNull();

        toggle_video(block);
        expect(root.querySelector('.player')).toBeNull();
        expect(block.querySelector('.playbutton')).not.toBeNull();
    });

    it('plays a mastodon gifv looped and muted, keeping its aspect ratio', () => {
        const root = stream(
            '<span class="play-video video-inline" data-id="mastodon-1" data-src="/v.mp4" ' +
                'data-media-type="gifv" data-width="400" data-height="300"></span>',
        );
        const block = root.querySelector('span') as HTMLElement;
        vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();

        toggle_video(block);
        const player = block.nextElementSibling as HTMLElement;
        const video = player.querySelector('video') as HTMLVideoElement;
        expect(video.loop && video.muted).toBe(true);
        expect(player.getAttribute('style')).toBe('padding-bottom:75.0000%');

        toggle_video(block);
        expect(root.querySelector('.player')).toBeNull();
    });
});
