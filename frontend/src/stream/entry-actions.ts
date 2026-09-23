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
import { hide_spinner, show_spinner } from '../ui/spinner';
import { _ } from '../util/i18n';
import { parse_id } from '../util/ids';
import { scroll_to_element } from '../util/scroll';
import { scaledown_images } from './images';

type ExpandableArticle = HTMLElement & {
    content_loaded?: boolean;
    content_expanded?: boolean;
};

/** The open entry menu. */
export const menu_state = {
    open: null as HTMLElement | null,
};

/** The menu switch of the entry a menu item belongs to. */
export function $M(entry: HTMLElement): HTMLElement {
    return $(
        '.entry-controls-switch',
        (entry.parentNode as HTMLElement).parentNode!.parentNode as HTMLElement,
    )[0] as HTMLElement;
}

export function hide_entry(this: HTMLElement, e?: JQuery.TriggeredEvent): false | void {
    if (e) {
        e.preventDefault();
    }
    if ($('span.favorite', $M(this).parentNode as HTMLElement).length) {
        alert(_('Unfavorite this entry before hiding it.'));
        return false;
    }
    const id = this.id.split('-')[1] as string;
    show_spinner($M(this));
    $.post(
        config.baseurl + 'api/hide',
        {
            entry: id,
        },
        function () {
            hide_spinner();
            $('#entry-' + id).fadeOut('normal', function () {
                $(this).after(
                    '<div id="hidden-' +
                        id +
                        '" class="entry-hidden"><em>' +
                        _('Entry hidden') +
                        '</em> - <a href="#" onclick="return gls.unhide_entry.call(this)">' +
                        _('Undo') +
                        '</a></div>',
                );
            });
        },
    );
}

export function unhide_entry(this: HTMLElement): boolean {
    const id = (this.parentNode as HTMLElement).id.split('-')[1] as string;
    show_spinner(this);
    $.post(
        config.baseurl + 'api/unhide',
        {
            entry: id,
        },
        function () {
            hide_spinner();
            $('#hidden-' + id).remove();
            $('#entry-' + id).fadeIn();
        },
    );
    return false;
}

export function favorite_entry(this: HTMLElement, e?: JQuery.TriggeredEvent): void {
    if (e) {
        e.preventDefault();
    }
    const that = this;
    const id = this.id.split('-')[1] as string;
    show_spinner($M(this));
    if (!$(this).hasClass('fav')) {
        $.post(
            config.baseurl + 'api/favorite',
            {
                entry: id,
            },
            function () {
                hide_spinner();
                $($M(that)).before('<span class="favorite"></span>');
                $(that).addClass('fav').html(_('Unfavorite'));
            },
        );
    } else {
        $.post(
            config.baseurl + 'api/unfavorite',
            {
                entry: id,
            },
            function () {
                hide_spinner();
                $('span.favorite', $M(that).parentNode as HTMLElement).remove();
                $(that).removeClass('fav').html(_('Favorite'));
            },
        );
    }
}

/** Opens the entry's stored HTML in the raw editor under its content. */
export function edit_raw_entry(this: HTMLElement, e?: JQuery.TriggeredEvent): void {
    if (e) {
        e.preventDefault();
    }
    const that = this;
    const id = this.id.split('-')[1] as string;
    show_spinner($M(this));
    $.post(
        config.baseurl + 'api/getcontent',
        {
            entry: id,
            raw: 1,
        },
        function (html: string) {
            hide_spinner();
            const ec = $(that).closest('article').find('.entry-content');
            const editor = $('#entry-editor');
            $('#edited-content').val(html);
            ec.after(editor);
            editor.fadeIn('normal', function () {
                scroll_to_element(editor, 400);
            });
        },
    );
}

/** The Save and Cancel buttons of the raw editor. */
export function editor_handler(this: HTMLElement): void {
    const op = this.getAttribute('name');
    if (op === 'cancel') {
        $('#entry-editor').fadeOut();
    } else if (op === 'save') {
        show_spinner(this);
        const article = $(this).closest('article').get(0) as HTMLElement;
        const id = parse_id(article.id)[1] as string;
        $.post(
            config.baseurl + 'api/putcontent',
            {
                entry: id,
                content: $('#edited-content').val(),
            },
            function (html: string) {
                hide_spinner();
                $('#entry-' + id + ' .entry-content').html(html);
            },
        );
    }
}

/** Shows or hides the content of an entry shown by its title only. */
export function expand_content(this: HTMLElement): boolean {
    const article = (this.parentNode as HTMLElement).parentNode as ExpandableArticle;
    if (article.content_loaded) {
        if (article.content_expanded) {
            $('div.entry-content', article).slideUp();
            article.content_expanded = false;
        } else {
            $('div.entry-content', article).slideDown();
            article.content_expanded = true;
        }
    } else {
        const id = parse_id(article.id)[1] as string;
        show_spinner(this);
        $.post(
            config.baseurl + 'api/getcontent',
            {
                entry: id,
            },
            function (html: string) {
                hide_spinner();
                $('div.entry-content', article).html(html).slideDown();
                article.content_loaded = true;
                article.content_expanded = true;
                scaledown_images($('img', article));
            },
        );
    }
    return false;
}

export function show_menu_controls(this: HTMLElement): boolean {
    hide_menu_controls();
    const s = $('.entry-controls', this.parentNode as HTMLElement);
    const pos = $(this).position();
    s.addClass('menu-expanded')
        .css({
            top: pos.top + 17,
            left: pos.left,
        })
        .show();
    menu_state.open = s[0] as HTMLElement;
    document.onclick = hide_menu_controls;

    const y_bottom = pos.top + (s.height() as number);
    const y_diff =
        y_bottom - ($(window).height() as number) - ($(document).scrollTop() as number);
    if (y_diff > -20) {
        s.css('top', pos.top - y_diff - 15 + 'px');
    }
    return false;
}

export function hide_menu_controls(): void {
    if (menu_state.open) {
        $(menu_state.open).hide().removeClass('menu-expanded');
    }
    document.onclick = null;
}
