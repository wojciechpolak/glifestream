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

import { _ } from '../util/i18n';
import { parse_id } from '../util/ids';
import { scroll_to_element } from '../util/scroll';

/** Audio providers by id prefix; user-scripts.js may add more. */
export const audio_embeds: Record<string, string> = {};

/** Video providers by id prefix; user-scripts.js may add or replace them. */
export const video_embeds: Record<string, GlsVideoProvider> = {
    youtube:
        '<iframe width="560" height="349" src="https://www.youtube.com/embed/{ID}?autoplay=1&rel=0" frameborder="0" allowfullscreen></iframe>',
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

function cleanup_video_player(wrapper: HTMLElement): void {
    const cleanup: unknown = $(wrapper).data('videoCleanup');
    if (typeof cleanup == 'function') {
        cleanup();
        $(wrapper).removeData('videoCleanup');
    }
}

/** The padding that keeps a player at the video's aspect ratio. */
function aspect_style(wrapper: HTMLElement): string {
    const width = Number($(wrapper).data('width'));
    const height = Number($(wrapper).data('height'));
    let style = '';
    if (width > 0 && height > 0) {
        style = 'padding-bottom:' + ((height / width) * 100).toFixed(4) + '%';
    }
    return style;
}

function render_atproto_video(wrapper: HTMLElement): GlsVideoEmbed | null {
    const playlist: string | undefined = $(wrapper).data('playlist');
    if (!playlist) {
        return null;
    }

    const video = document.createElement('video');
    video.autoplay = true;
    video.controls = true;
    video.preload = 'metadata';
    video.playsInline = true;

    const poster: string | undefined = $(wrapper).data('poster');
    if (poster) {
        video.poster = poster;
    }

    const style = aspect_style(wrapper);

    if (can_play_hls(video)) {
        video.src = playlist;
        return {
            node: video,
            style: style,
            onMount: function () {
                video.play().catch(function () {});
            },
        };
    }

    return null;
}

function render_mastodon_video(wrapper: HTMLElement): GlsVideoEmbed | null {
    const src: string | undefined = $(wrapper).data('src');
    if (!src) {
        return null;
    }

    const video = document.createElement('video');
    video.autoplay = true;
    video.controls = true;
    video.preload = 'metadata';
    video.playsInline = true;
    video.src = src;

    const poster: string | undefined = $(wrapper).data('poster');
    if (poster) {
        video.poster = poster;
    }

    if ($(wrapper).data('mediaType') === 'gifv') {
        video.loop = true;
        video.muted = true;
    }

    const style = aspect_style(wrapper);

    return {
        node: video,
        style: style,
        onMount: function () {
            video.play().catch(function () {});
        },
    };
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

/** The block a video player goes after: a table cell's table, or itself. */
function $VC(obj: HTMLElement): JQuery {
    if ((obj.parentNode as HTMLElement).tagName === 'TD') {
        obj = (obj.parentNode as HTMLElement).parentNode!.parentNode!
            .parentNode as HTMLElement;
        if (obj.className === 'vc') {
            return $(obj);
        }
    }
    return $(obj);
}

function play_video(this: HTMLElement): boolean {
    const a = parse_id($(this).data('id') || this.id);
    const type = a[0];
    const id = a[1] as string;

    const embed = render_video_embed(this, type, id);
    if (!embed) {
        return true;
    }

    $('.playbutton', this).removeClass('playbutton').addClass('stopbutton');
    const $player = $('<div class="player video ' + type + '"></div>');
    if (embed.style) {
        $player.attr('style', embed.style);
    }
    if (embed.html) {
        $player.html(embed.html);
    } else if (embed.node) {
        $player.append(embed.node);
    }
    $VC(this).after($player);
    if (typeof embed.onMount == 'function') {
        embed.onMount($player[0] as HTMLElement);
    }
    $('a', this).blur();
    scroll_to_element(this);
    return false;
}

function stop_video(this: HTMLElement): boolean {
    cleanup_video_player(this);
    $('.player', $VC(this).parent()).remove();
    $('.stopbutton', this).removeClass('stopbutton').addClass('playbutton');
    $('a', this).blur();
    return false;
}

/** Opens or closes the player of a play-video block. */
export function toggle_video(this: HTMLElement): boolean {
    const $this = $(this);
    if (!$this.hasClass('video-inline')) {
        if ($('.playbutton', this).length) {
            return play_video.call(this);
        } else {
            return stop_video.call(this);
        }
    } else {
        if (!$this.data('play')) {
            $this.data('play', true);
            return play_video.call(this);
        } else {
            $this.data('play', false);
            return stop_video.call(this);
        }
    }
}

/** Opens or closes the player of a play-audio link. */
export function play_audio(this: HTMLElement, e: JQuery.TriggeredEvent): boolean {
    if (e.which && e.which !== 1) {
        return false;
    }
    const a = parse_id($(this).data('id') || this.id);
    const type = a[0];
    $('a', this).blur();

    const parent = this.parentNode as HTMLElement;
    if ($('.player', parent).length) {
        $('.player', parent).remove();
        return false;
    }

    let embed: string;
    if (type === 'audio') {
        embed =
            '<audio src="' +
            $('a', this).attr('href') +
            '" controls="true">' +
            _('Your browser does not support it.') +
            '</audio>';
    } else if (type in audio_embeds) {
        embed = audio_embeds[type] as string;
    } else if (type === 'thesixtyone') {
        return false; // prevent navigating to a defunct site
    } else {
        return true;
    }

    let id;
    if (type === 'thesixtyone') {
        const data = (a[1] as string).split('-');
        const artist = data[0] as string;
        id = data[1];
        embed = embed.replace('{ARTIST}', artist);
    } else if (type === 'mp3') {
        id = $('a', this).attr('href');
    } else {
        id = a[1];
    }

    embed = embed.replace(/{ID}/g, id as string);

    $('.player').remove();
    $(parent).append('<div class="player audio">' + embed + '</div>');
    if (type === 'audio') {
        const $au = $(parent).find('audio');
        if ($au.length) {
            void ($au[0] as HTMLAudioElement).play();
        }
    }
    return false;
}

/** Turns video links into players and audio files into play-audio links. */
export function alter_html(ctx: HTMLElement | JQuery): void {
    $<HTMLAnchorElement>('.thumbnails a', ctx).each(function () {
        let id = '';
        try {
            if (this.href.indexOf('https://www.youtube.com/watch') === 0) {
                id = 'youtube-' + this.href.substr(32);
            } else if (this.href.indexOf('https://vimeo.com/') === 0) {
                id = 'vimeo-' + this.href.substr(18);
            } else if (this.href.indexOf('http://www.youtube.com/watch') === 0) {
                id = 'youtube-' + this.href.substr(31);
            } else if (this.href.indexOf('http://vimeo.com/') === 0) {
                id = 'vimeo-' + this.href.substr(17);
            }
            if (id) {
                $(this).wrap('<div id="' + id + '" class="play-video"></div>');
                $(this).after('<div class="playbutton"></div>');
            }
        } catch {
            // Keep going with the next link.
        }
    });

    $('.files a[href$=".mp3"]', ctx).wrap(
        '<span data-id="audio-x" class="play-audio"></span>',
    );
    $('.files a[href$=".ogg"]', ctx).wrap(
        '<span data-id="audio-x" class="play-audio"></span>',
    );

    if (typeof window.user_alter_html == 'function') {
        window.user_alter_html(ctx);
    }
}
