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
import { Lightbox } from '../ui/lightbox';
import { fade_in, fade_out } from '../ui/fx';
import { init_pull_to_refresh } from '../ui/pull-to-refresh';
import { delegate, listen } from '../util/dom';
import { _ } from '../util/i18n';
import { follow_href } from '../util/navigation';
import { scroll_to_top } from '../util/scroll';
import { init_calendar } from './calendar';
import {
    edit_entry,
    init_editor,
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
import { render_maps, show_map } from './maps';
import {
    alter_html,
    audio_embeds,
    play_audio,
    toggle_video,
    video_embeds,
} from './media';
import { DEFAULT_SHARING_SITES, share_state, shareit_entry } from './share';
import { init_shortcuts } from './shortcuts';
import { change_theme, toggle_reblogs } from './sidebar';
import { stream_state } from './state';

/** The clicks on the entries of the stream, listened for once on it. */
function init_entry_controls(stream: HTMLElement): void {
    delegate(stream, 'click', 'span.favorite-control', favorite_entry);
    delegate(stream, 'click', 'span.hide-control', hide_entry);
    delegate(stream, 'click', 'span.edit-control', edit_entry);
    delegate(stream, 'click', 'span.editRaw-control', edit_raw_entry);
    delegate(stream, 'click', 'a.shareit', shareit_entry);
    delegate(stream, 'click', 'a.show-map', show_map);
    delegate(stream, 'click', 'a.expand-content', expand_content);
    delegate(stream, 'click', 'span.entry-controls-switch', show_menu_controls);
    delegate(stream, 'click', 'div.play-video,span.play-video', toggle_video);
    delegate(stream, 'click', 'span.play-audio', play_audio);
}

function init_search(): void {
    listen('form[name=searchform]', 'submit', function () {
        const s = document.querySelector<HTMLInputElement>('input[name=s]');
        return !!s && s.value !== '';
    });
    listen('#search-submit', 'click', function () {
        for (const form of document.querySelectorAll<HTMLFormElement>(
            'form[name=searchform]',
        )) {
            form.requestSubmit();
        }
    });
}

function init_scroll_to_top(): void {
    const buttons = document.querySelectorAll<HTMLElement>('.scroll-to-top');
    window.addEventListener('scroll', function () {
        for (const button of buttons) {
            void (window.scrollY > 100 ? fade_in(button) : fade_out(button));
        }
    });
    for (const button of buttons) {
        listen(button, 'click', function () {
            scroll_to_top();
            return false;
        });
    }
}

/** Sets up a stream page: entries, sidebar, composer and shortcuts. */
export function init_stream(): void {
    Lightbox.scan();
    // Pages such as the login form share the sidebar but have no stream.
    const stream = document.getElementById('stream');
    if (stream) {
        alter_html(stream);
        init_entry_controls(stream);
        render_maps(stream);
    }

    listen('#sidebar-toggle', 'click', function (toggle) {
        const expanded = !!document
            .getElementById('sidebar')
            ?.classList.toggle('expanded');
        toggle.setAttribute('aria-expanded', String(expanded));
    });

    listen('#toggle-reblogs', 'click', toggle_reblogs);
    listen('#change-theme', 'click', change_theme);
    listen('div.lists select', 'change', function (select) {
        const value = (select as HTMLSelectElement).value;
        window.location.href =
            config.baseurl + (value !== '' ? 'list/' + value + '/' : '');
    });
    delegate(document, 'click', '#entry-editor input[type=button]', editor_handler);

    init_calendar();

    scaledown_images();

    const scope = stream || document;
    stream_state.articles = Array.from(scope.querySelectorAll<HTMLElement>('article'));
    stream_state.nav_next = Array.from(
        scope.querySelectorAll<HTMLAnchorElement>('nav a.next'),
    );
    init_shortcuts();

    for (const audio of scope.querySelectorAll<HTMLElement>('span.play-audio')) {
        audio.title = _('Click and Listen');
    }

    init_search();

    listen('#ashare', 'click', open_sharing);
    listen('#expand-sharing', 'click', open_more_sharing_options);
    listen('#update', 'click', share);
    listen('#post', 'click', share);

    if (typeof window.continuous_reading !== 'undefined') {
        stream_state.continuous_reading = parseInt(
            String(window.continuous_reading),
            10,
        );
    }
    for (const link of stream_state.nav_next) {
        listen(
            link,
            'click',
            stream_state.continuous_reading ? load_entries : follow_href,
        );
    }

    init_editor();

    Object.assign(audio_embeds, window.audio_embeds);
    Object.assign(video_embeds, window.video_embeds);

    delegate(document, 'keypress', 'span.link', function (link, e) {
        if (e.key === 'Enter') {
            link.click();
        }
    });

    share_state.sites = window.social_sharing_sites || DEFAULT_SHARING_SITES;

    init_scroll_to_top();

    init_pull_to_refresh();

    init_share_target();
}
