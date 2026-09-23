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

import { config } from '../config';
import { Graybox } from '../ui/graybox';
import { init_pull_to_refresh } from '../ui/pull-to-refresh';
import { _ } from '../util/i18n';
import { follow_href } from '../util/navigation';
import { scroll_to_top } from '../util/scroll';
import { init_calendar } from './calendar';
import {
    edit_entry,
    init_quill,
    init_share_target,
    open_more_sharing_options,
    open_sharing,
    share,
} from './composer';
import { load_entries } from './continuous';
import {
    edit_raw_entry,
    editor_handler,
    expand_content,
    favorite_entry,
    hide_entry,
    show_menu_controls,
} from './entry-actions';
import { scaledown_images } from './images';
import { render_map, show_map } from './maps';
import {
    alter_html,
    audio_embeds,
    play_audio,
    toggle_video,
    video_embeds,
} from './media';
import { DEFAULT_SHARING_SITES, share_state, shareit_entry } from './share';
import { kshortcuts } from './shortcuts';
import { change_theme, toggle_reblogs } from './sidebar';
import { stream_state } from './state';

type SearchInput = HTMLInputElement & { PLACEHOLDER?: string | null };

function focus_search(this: GlobalEventHandlers): void {
    const input = this as SearchInput;
    if (input.value === input.PLACEHOLDER) {
        $(input).val('').removeClass('blur');
    }
}

function blur_search(this: GlobalEventHandlers): void {
    const input = this as SearchInput;
    if (input.value === '') {
        $(input)
            .val(input.PLACEHOLDER as string)
            .addClass('blur');
    }
}

/** A placeholder for browsers without the attribute. */
function set_placeholder(inputs: JQuery, defval?: string): void {
    const has = 'placeholder' in document.createElement('input');
    for (let i = 0; i < inputs.length; i++) {
        const input = inputs[i] as SearchInput;
        input.PLACEHOLDER = defval || input.getAttribute('placeholder');
        if (!has) {
            input.autocomplete = 'off';
            input.onfocus = focus_search;
            input.onblur = blur_search;
            if (input.value === '' || input.value === input.PLACEHOLDER) {
                $(input)
                    .val(input.PLACEHOLDER as string)
                    .addClass('blur');
            }
        }
    }
}

/** Sets up a stream page: entries, sidebar, composer and shortcuts. */
export function init_stream(): void {
    Graybox.scan();
    const stream = $('#stream').get(0) as HTMLElement;
    alter_html(stream);

    $(stream).on('click', 'span.favorite-control', favorite_entry);
    $(stream).on('click', 'span.hide-control', hide_entry);
    $(stream).on('click', 'span.edit-control', edit_entry);
    $(stream).on('click', 'span.editRaw-control', edit_raw_entry);
    $(stream).on('click', 'a.shareit', shareit_entry);
    $(stream).on('click', 'a.show-map', show_map);
    $(stream).on('click', 'a.expand-content', expand_content);
    $(stream).on('click', 'span.entry-controls-switch', show_menu_controls);
    $(stream).on('click', 'div.play-video,span.play-video', toggle_video);
    $(stream).on('click', 'span.play-audio', play_audio);

    $('a.map', stream).each(render_map);

    $('#sidebar-toggle').click(function () {
        $('#sidebar').toggleClass('expanded');
        $('i', this).toggleClass('fa-chevron-up fa-chevron-down');
    });

    $('#toggle-reblogs').click(toggle_reblogs);
    $('#change-theme').click(change_theme);
    $<HTMLSelectElement>('div.lists select').change(function () {
        if (this.value !== '') {
            window.location.href = config.baseurl + 'list/' + this.value + '/';
        }
    });
    $(document).on('click', '#entry-editor input[type=button]', editor_handler);

    init_calendar();

    scaledown_images();

    stream_state.articles = $('article', stream);
    stream_state.nav_next = $<HTMLAnchorElement>('nav a.next', stream);
    document.onkeypress = kshortcuts;

    $('span.play-audio', stream).each(function () {
        this.title = _('Click and Listen');
    });

    $('#status, #edited-content, form input[type=search]')
        .focus(function () {
            document.onkeypress = null;
        })
        .blur(function () {
            document.onkeypress = kshortcuts;
        });

    $('form[name=searchform]').submit(function () {
        const s = $('input[name=s]').get(0) as SearchInput | undefined;
        if (s && s.value !== '' && s.value !== s.PLACEHOLDER) {
            return true;
        }
        return false;
    });
    $('#search-submit').click(function () {
        $('form[name=searchform]').submit();
    });
    set_placeholder($('input[placeholder]'));

    $('#ashare').click(open_sharing);
    $('#expand-sharing').click(open_more_sharing_options);
    $('#update, #post').click(share);

    if (typeof window.continuous_reading !== 'undefined') {
        stream_state.continuous_reading = parseInt(
            String(window.continuous_reading),
            10,
        );
    }
    stream_state.nav_next.click(
        stream_state.continuous_reading ? load_entries : follow_href,
    );

    init_quill();

    if (window.audio_embeds) {
        $.extend(audio_embeds, window.audio_embeds);
    }
    if (window.video_embeds) {
        $.extend(video_embeds, window.video_embeds);
    }

    $(document).on('keypress', 'span.link', function (e) {
        if (e.keyCode === 13) {
            $(this).click();
        }
    });

    share_state.sites = window.social_sharing_sites || DEFAULT_SHARING_SITES;

    const $scrollToTopButton = $('.scroll-to-top');

    $(window).scroll(function () {
        if (($(this).scrollTop() as number) > 100) {
            $scrollToTopButton.fadeIn();
        } else {
            $scrollToTopButton.fadeOut();
        }
    });

    $scrollToTopButton.click(function () {
        scroll_to_top();
        return false;
    });

    init_pull_to_refresh();

    init_share_target();
}
