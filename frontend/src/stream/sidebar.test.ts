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

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { config } from '../config';
import { read_cookie } from '../util/cookies';
import { change_theme, init_theme_menu } from './sidebar';

/** The listeners the tested code added to the document, removed after each test. */
const added: [string, EventListenerOrEventListenerObject][] = [];
const reload = vi.fn();

const MENU = `
    <div class="change-theme-wrapper">
      <span tabindex="0" id="change-theme" class="link" aria-expanded="false">Change theme</span>
      <ul id="theme-menu">
        <li><span tabindex="0" class="link" data-theme="default">Default</span></li>
        <li><span tabindex="0" class="link" data-theme="riso" aria-current="true">Riso</span></li>
        <li><span tabindex="0" class="link" data-theme="dotfiles">Dotfiles</span></li>
      </ul>
    </div>
    <h1>The Stream</h1>`;

function theme_switch(): HTMLElement {
    return document.getElementById('change-theme') as HTMLElement;
}

function menu(): HTMLElement {
    return document.getElementById('theme-menu') as HTMLElement;
}

function choice(name: string): HTMLElement {
    return document.querySelector(`[data-theme="${name}"]`) as HTMLElement;
}

function click(target: Element): void {
    target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
}

function is_open(): boolean {
    return menu().classList.contains('menu-expanded');
}

beforeEach(() => {
    const add = document.addEventListener.bind(document);
    vi.spyOn(document, 'addEventListener').mockImplementation(
        (type, listener, options) => {
            added.push([type, listener]);
            add(type, listener, options);
        },
    );
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    window.__glsReloadHandler = reload;
    config.baseurl = '/';
    config.themes = ['default', 'riso', 'dotfiles'];
    document.cookie = 'gls-theme=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
});

afterEach(() => {
    for (const [type, listener] of added.splice(0)) {
        document.removeEventListener(type, listener);
    }
    vi.restoreAllMocks();
    reload.mockReset();
    delete window.__glsReloadHandler;
    config.themes = [];
    document.body.innerHTML = '';
});

describe('change_theme with a list of themes', () => {
    beforeEach(() => {
        document.body.innerHTML = MENU;
        init_theme_menu();
    });

    it('opens and closes the list', () => {
        change_theme();
        expect(is_open()).toBe(true);
        expect(theme_switch().getAttribute('aria-expanded')).toBe('true');

        change_theme();
        expect(is_open()).toBe(false);
        expect(theme_switch().getAttribute('aria-expanded')).toBe('false');
        expect(reload).not.toHaveBeenCalled();
    });

    it('switches to the theme picked', () => {
        change_theme();
        click(choice('dotfiles'));
        expect(read_cookie('gls-theme')).toBe('dotfiles');
        expect(reload).toHaveBeenCalledOnce();
        expect(is_open()).toBe(false);
    });

    it('only closes on the theme in use', () => {
        change_theme();
        click(choice('riso'));
        expect(read_cookie('gls-theme')).toBeNull();
        expect(reload).not.toHaveBeenCalled();
        expect(is_open()).toBe(false);
        expect(document.activeElement).toBe(theme_switch());
    });

    it('closes on a click elsewhere on the page', () => {
        change_theme();
        click(document.querySelector('h1') as HTMLElement);
        expect(is_open()).toBe(false);
        expect(theme_switch().getAttribute('aria-expanded')).toBe('false');
    });

    it('closes on Escape and gives the focus back to its switch', () => {
        change_theme();
        choice('default').focus();
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
        expect(is_open()).toBe(false);
        expect(document.activeElement).toBe(theme_switch());
    });
});

describe('change_theme without a list', () => {
    beforeEach(() => {
        document.body.innerHTML =
            '<span tabindex="0" id="change-theme" class="link">Change theme</span>';
        config.themes = ['default', 'riso'];
        init_theme_menu();
    });

    it('switches to the other theme and back', () => {
        change_theme();
        expect(read_cookie('gls-theme')).toBe('riso');
        change_theme();
        expect(read_cookie('gls-theme')).toBe('default');
        expect(reload).toHaveBeenCalledTimes(2);
    });

    it('takes a cookie it does not know for the first theme', () => {
        document.cookie = 'gls-theme=gone; path=/';
        change_theme();
        expect(read_cookie('gls-theme')).toBe('riso');
    });
});
