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
import { post_text } from '../http';
import { fade_in, fade_out, hide, show, slide_down, slide_up } from '../ui/fx';
import { hide_spinner, show_spinner } from '../ui/spinner';
import { h, listen } from '../util/dom';
import { _ } from '../util/i18n';
import { parse_id } from '../util/ids';
import { scroll_to_element } from '../util/scroll';
import { scaledown_images } from './images';

/** The open entry menu. */
export const menu_state = {
    open: null as HTMLElement | null,
};

/** Entries shown by title whose content has loaded: whether it is open. */
const expanded = new WeakMap<HTMLElement, boolean>();

/** The menu switch of the entry a menu item belongs to. */
export function $M(entry: HTMLElement): HTMLElement {
    const article = (entry.parentNode as HTMLElement).parentNode!
        .parentNode as HTMLElement;
    return article.querySelector('.entry-controls-switch') as HTMLElement;
}

function entry_id(control: HTMLElement): string {
    return control.id.split('-')[1] as string;
}

export function hide_entry(control: HTMLElement, e?: Event): false | void {
    if (e) {
        e.preventDefault();
    }
    if (($M(control).parentNode as HTMLElement).querySelector('span.favorite')) {
        alert(_('Unfavorite this entry before hiding it.'));
        return false;
    }
    const id = entry_id(control);
    show_spinner($M(control));
    void post_text(config.baseurl + 'api/hide', { entry: id }).then(async (html) => {
        if (html === null) {
            return;
        }
        hide_spinner();
        const entry = document.getElementById('entry-' + id);
        if (entry) {
            await fade_out(entry);
            entry.after(hidden_notice(id));
        }
    });
}

/** What stands in for a hidden entry, with an Undo link. */
function hidden_notice(id: string): HTMLElement {
    const undo = h('a', { href: '#' }, [_('Undo')]);
    listen(undo, 'click', unhide_entry);
    return h('div', { id: 'hidden-' + id, className: 'entry-hidden' }, [
        h('em', null, [_('Entry hidden')]),
        ' - ',
        undo,
    ]);
}

export function unhide_entry(link: HTMLElement): boolean {
    const id = (link.parentNode as HTMLElement).id.split('-')[1] as string;
    show_spinner(link);
    void post_text(config.baseurl + 'api/unhide', { entry: id }).then((html) => {
        if (html === null) {
            return;
        }
        hide_spinner();
        document.getElementById('hidden-' + id)?.remove();
        const entry = document.getElementById('entry-' + id);
        if (entry) {
            void fade_in(entry);
        }
    });
    return false;
}

export function favorite_entry(control: HTMLElement, e?: Event): void {
    if (e) {
        e.preventDefault();
    }
    const id = entry_id(control);
    show_spinner($M(control));
    if (!control.classList.contains('fav')) {
        void post_text(config.baseurl + 'api/favorite', { entry: id }).then((html) => {
            if (html === null) {
                return;
            }
            hide_spinner();
            $M(control).before(h('span', { className: 'favorite' }));
            control.classList.add('fav');
            control.textContent = _('Unfavorite');
        });
    } else {
        void post_text(config.baseurl + 'api/unfavorite', { entry: id }).then(
            (html) => {
                if (html === null) {
                    return;
                }
                hide_spinner();
                ($M(control).parentNode as HTMLElement)
                    .querySelector('span.favorite')
                    ?.remove();
                control.classList.remove('fav');
                control.textContent = _('Favorite');
            },
        );
    }
}

/** Opens the entry's stored HTML in the raw editor under its content. */
export function edit_raw_entry(control: HTMLElement, e?: Event): void {
    if (e) {
        e.preventDefault();
    }
    const id = entry_id(control);
    show_spinner($M(control));
    void post_text(config.baseurl + 'api/getcontent', { entry: id, raw: 1 }).then(
        async (html) => {
            if (html === null) {
                return;
            }
            hide_spinner();
            const content = control.closest('article')?.querySelector('.entry-content');
            const editor = document.getElementById('entry-editor') as HTMLElement;
            (document.getElementById('edited-content') as HTMLTextAreaElement).value =
                html;
            content?.after(editor);
            await fade_in(editor);
            scroll_to_element(editor, 400);
        },
    );
}

/** The Save and Cancel buttons of the raw editor. */
export function editor_handler(button: HTMLElement): void {
    const op = button.getAttribute('name');
    if (op === 'cancel') {
        void fade_out(document.getElementById('entry-editor') as HTMLElement);
    } else if (op === 'save') {
        show_spinner(button);
        const article = button.closest('article') as HTMLElement;
        const id = parse_id(article.id)[1] as string;
        const content = (
            document.getElementById('edited-content') as HTMLTextAreaElement
        ).value;
        void post_text(config.baseurl + 'api/putcontent', { entry: id, content }).then(
            (html) => {
                if (html === null) {
                    return;
                }
                hide_spinner();
                for (const el of document.querySelectorAll(
                    '#entry-' + id + ' .entry-content',
                )) {
                    el.innerHTML = html;
                }
            },
        );
    }
}

function entry_contents(article: HTMLElement): NodeListOf<HTMLElement> {
    return article.querySelectorAll<HTMLElement>('div.entry-content');
}

/** Shows or hides the content of an entry shown by its title only. */
export function expand_content(link: HTMLElement): boolean {
    const article = (link.parentNode as HTMLElement).parentNode as HTMLElement;
    const open = expanded.get(article);
    if (open !== undefined) {
        for (const content of entry_contents(article)) {
            void (open ? slide_up(content) : slide_down(content));
        }
        expanded.set(article, !open);
        return false;
    }
    const id = parse_id(article.id)[1] as string;
    show_spinner(link);
    void post_text(config.baseurl + 'api/getcontent', { entry: id }).then((html) => {
        if (html === null) {
            return;
        }
        hide_spinner();
        for (const content of entry_contents(article)) {
            content.innerHTML = html;
            void slide_down(content);
        }
        expanded.set(article, true);
        scaledown_images(article.querySelectorAll('img'));
    });
    return false;
}

/** Where jQuery's .position() puts an element: inside its positioned parent. */
function position(el: HTMLElement): { top: number; left: number } {
    let parent = el.offsetParent as HTMLElement | null;
    while (parent && getComputedStyle(parent).position === 'static') {
        parent = parent.offsetParent as HTMLElement | null;
    }
    const rect = el.getBoundingClientRect();
    let top = rect.top;
    let left = rect.left;
    if (parent && parent !== document.documentElement) {
        const parent_rect = parent.getBoundingClientRect();
        const parent_style = getComputedStyle(parent);
        top -= parent_rect.top + parseFloat(parent_style.borderTopWidth);
        left -= parent_rect.left + parseFloat(parent_style.borderLeftWidth);
    } else {
        top += window.scrollY;
        left += window.scrollX;
    }
    const style = getComputedStyle(el);
    return {
        top: top - parseFloat(style.marginTop),
        left: left - parseFloat(style.marginLeft),
    };
}

/** An element's content height, inside its padding and border. */
function content_height(el: HTMLElement): number {
    const style = getComputedStyle(el);
    const edges = [
        style.paddingTop,
        style.paddingBottom,
        style.borderTopWidth,
        style.borderBottomWidth,
    ].reduce((sum, value) => sum + (parseFloat(value) || 0), 0);
    return el.offsetHeight - edges;
}

export function show_menu_controls(control: HTMLElement): boolean {
    hide_menu_controls();
    const menus = (control.parentNode as HTMLElement).querySelectorAll<HTMLElement>(
        '.entry-controls',
    );
    const menu = menus[0];
    if (!menu) {
        return false;
    }
    const pos = position(control);
    for (const m of menus) {
        m.classList.add('menu-expanded');
        m.style.top = pos.top + 17 + 'px';
        m.style.left = pos.left + 'px';
        show(m);
    }
    menu_state.open = menu;
    document.addEventListener('click', hide_menu_controls);

    const y_bottom = pos.top + content_height(menu);
    const y_diff = y_bottom - document.documentElement.clientHeight - window.scrollY;
    if (y_diff > -20) {
        for (const m of menus) {
            m.style.top = pos.top - y_diff - 15 + 'px';
        }
    }
    return false;
}

export function hide_menu_controls(): void {
    if (menu_state.open) {
        hide(menu_state.open);
        menu_state.open.classList.remove('menu-expanded');
    }
    document.removeEventListener('click', hide_menu_controls);
}
