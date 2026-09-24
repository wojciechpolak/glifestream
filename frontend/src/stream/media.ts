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

import { h } from '../util/dom';
import { _ } from '../util/i18n';
import { parse_id } from '../util/ids';
import { scroll_to_element } from '../util/scroll';

/** Audio providers by id prefix; user-scripts.js may add more. */
export const audio_embeds: Record<string, string> = {};

/** Video providers by id prefix; user-scripts.js may add or replace them. */
export const video_embeds: Record<string, GlsVideoProvider> = {
    // YouTube refuses to play (error 153) without a Referer, which the page's
    // same-origin Referrer-Policy withholds; send it the origin only.
    youtube:
        '<iframe width="560" height="349" src="https://www.youtube.com/embed/{ID}?autoplay=1&rel=0" referrerpolicy="strict-origin-when-cross-origin" frameborder="0" allowfullscreen></iframe>',
    vimeo: '<iframe width="560" height="315" src="https://player.vimeo.com/video/{ID}?autoplay=1" frameborder="0" allowfullscreen></iframe>',
    dailymotion:
        '<iframe width="560" height="315" src="https://www.dailymotion.com/embed/video/{ID}?autoplay=1" frameborder="0"></iframe>',
    atproto: render_atproto_video,
    mastodon: render_mastodon_video,
};

export function can_play_hls(video: HTMLVideoElement): boolean {
    return !!(
        video.canPlayType('application/vnd.apple.mpegurl') ||
        video.canPlayType('application/x-mpegURL')
    );
}

/** The padding that keeps a player at the video's aspect ratio. */
function aspect_style(wrapper: HTMLElement): string {
    const width = Number(wrapper.dataset['width']);
    const height = Number(wrapper.dataset['height']);
    let style = '';
    if (width > 0 && height > 0) {
        style = 'padding-bottom:' + ((height / width) * 100).toFixed(4) + '%';
    }
    return style;
}

/** A video element that plays as soon as it is shown. */
function autoplay_video(src: string, poster: string | undefined): HTMLVideoElement {
    const video = document.createElement('video');
    video.autoplay = true;
    video.controls = true;
    video.preload = 'metadata';
    video.playsInline = true;
    video.src = src;
    if (poster) {
        video.poster = poster;
    }
    return video;
}

function mount(video: HTMLVideoElement, wrapper: HTMLElement): GlsVideoEmbed {
    return {
        node: video,
        style: aspect_style(wrapper),
        onMount: function () {
            video.play().catch(function () {});
        },
    };
}

function render_atproto_video(wrapper: HTMLElement): GlsVideoEmbed | null {
    const playlist = wrapper.dataset['playlist'];
    if (!playlist) {
        return null;
    }
    const video = autoplay_video(playlist, wrapper.dataset['poster']);
    return can_play_hls(video) ? mount(video, wrapper) : null;
}

function render_mastodon_video(wrapper: HTMLElement): GlsVideoEmbed | null {
    const src = wrapper.dataset['src'];
    if (!src) {
        return null;
    }
    const video = autoplay_video(src, wrapper.dataset['poster']);
    if (wrapper.dataset['mediaType'] === 'gifv') {
        video.loop = true;
        video.muted = true;
    }
    return mount(video, wrapper);
}

function render_video_embed(
    wrapper: HTMLElement,
    type: string,
    id: string,
): GlsVideoEmbed | null {
    const provider = video_embeds[type];
    if (typeof provider == 'string') {
        return {
            html: provider.replace(/{ID}/g, id),
        };
    }
    if (typeof provider == 'function') {
        return provider(wrapper, id);
    }
    return null;
}

/** The block a video player goes after: the table a cell is in, or itself. */
function video_container(obj: HTMLElement): HTMLElement {
    if ((obj.parentNode as HTMLElement).tagName === 'TD') {
        return (obj.parentNode as HTMLElement).parentNode!.parentNode!
            .parentNode as HTMLElement;
    }
    return obj;
}

function blur_links(el: HTMLElement): void {
    for (const a of el.querySelectorAll('a')) {
        a.blur();
    }
}

function swap_class(el: HTMLElement, from: string, to: string): void {
    for (const button of el.querySelectorAll('.' + from)) {
        button.classList.replace(from, to);
    }
}

/** The provider and id of a player block: its data-id, or else its id. */
function media_id(el: HTMLElement): ReturnType<typeof parse_id> {
    return parse_id(el.dataset['id'] || el.id);
}

function play_video(el: HTMLElement): boolean {
    const a = media_id(el);
    const type = a[0];
    const id = a[1] as string;

    const embed = render_video_embed(el, type, id);
    if (!embed) {
        return true;
    }

    swap_class(el, 'playbutton', 'stopbutton');
    const player = h('div', { className: 'player video ' + type });
    if (embed.style) {
        player.setAttribute('style', embed.style);
    }
    if (embed.html) {
        player.innerHTML = embed.html;
    } else if (embed.node) {
        player.append(embed.node);
    }
    video_container(el).after(player);
    if (typeof embed.onMount == 'function') {
        embed.onMount(player);
    }
    blur_links(el);
    scroll_to_element(el);
    return false;
}

function stop_video(el: HTMLElement): boolean {
    const parent = video_container(el).parentElement;
    for (const player of parent?.querySelectorAll('.player') || []) {
        player.remove();
    }
    swap_class(el, 'stopbutton', 'playbutton');
    blur_links(el);
    return false;
}

/** The inline players that are playing. */
const playing = new WeakSet<HTMLElement>();

/** Opens or closes the player of a play-video block. */
export function toggle_video(block: HTMLElement): boolean {
    if (!block.classList.contains('video-inline')) {
        if (block.querySelector('.playbutton')) {
            return play_video(block);
        }
        return stop_video(block);
    }
    if (!playing.has(block)) {
        playing.add(block);
        return play_video(block);
    }
    playing.delete(block);
    return stop_video(block);
}

/** Opens or closes the player of a play-audio link. */
export function play_audio(block: HTMLElement, e: MouseEvent): boolean {
    if (e.button !== 0) {
        return false;
    }
    const a = media_id(block);
    const type = a[0];
    blur_links(block);

    const parent = block.parentNode as HTMLElement;
    const open = parent.querySelectorAll('.player');
    if (open.length) {
        for (const player of open) {
            player.remove();
        }
        return false;
    }

    const href = block.querySelector('a')?.getAttribute('href') || '';
    let embed: string | HTMLAudioElement;
    if (type === 'audio') {
        embed = h('audio', { src: href, controls: true }, [
            _('Your browser does not support it.'),
        ]);
    } else if (type in audio_embeds) {
        embed = audio_embeds[type] as string;
    } else if (type === 'thesixtyone') {
        return false; // prevent navigating to a defunct site
    } else {
        return true;
    }

    if (typeof embed == 'string') {
        const id = type === 'mp3' ? href : (a[1] as string);
        embed = embed.replace(/{ID}/g, id);
    }

    for (const player of document.querySelectorAll('.player')) {
        player.remove();
    }
    const player = h('div', { className: 'player audio' });
    if (typeof embed == 'string') {
        player.innerHTML = embed;
    } else {
        player.append(embed);
    }
    parent.append(player);
    if (type === 'audio') {
        void (embed as HTMLAudioElement).play();
    }
    return false;
}

/** Wraps `el` in `wrapper`, where `el` was. */
function wrap(el: Element, wrapper: HTMLElement): HTMLElement {
    el.before(wrapper);
    wrapper.append(el);
    return wrapper;
}

/** The provider id of a video page link, or '' for other links. */
function video_id(href: string): string {
    if (href.indexOf('https://www.youtube.com/watch') === 0) {
        return 'youtube-' + href.slice(32);
    } else if (href.indexOf('https://vimeo.com/') === 0) {
        return 'vimeo-' + href.slice(18);
    } else if (href.indexOf('http://www.youtube.com/watch') === 0) {
        return 'youtube-' + href.slice(31);
    } else if (href.indexOf('http://vimeo.com/') === 0) {
        return 'vimeo-' + href.slice(17);
    }
    return '';
}

/** A batch of entries shown: one element, or the entries continuous reading added. */
export type Shown = HTMLElement | HTMLElement[];

/** Turns video links into players and audio files into play-audio links. */
export function alter_html(ctx: Shown): void {
    const roots = Array.isArray(ctx) ? ctx : [ctx];
    for (const root of roots) {
        for (const link of root.querySelectorAll<HTMLAnchorElement>('.thumbnails a')) {
            const id = video_id(link.href);
            if (id) {
                wrap(link, h('div', { id, className: 'play-video' }));
                link.after(h('div', { className: 'playbutton' }));
            }
        }
        const audio = root.querySelectorAll(
            '.files a[href$=".mp3"], .files a[href$=".ogg"]',
        );
        for (const link of audio) {
            const span = h('span', { className: 'play-audio' });
            span.dataset['id'] = 'audio-x';
            wrap(link, span);
        }
    }

    if (typeof window.user_alter_html == 'function') {
        window.user_alter_html(ctx);
    }
}
