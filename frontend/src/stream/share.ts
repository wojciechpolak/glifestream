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
import { Overlay } from '../ui/overlay';
import { hide_spinner, show_spinner } from '../ui/spinner';
import { MDOM, h, listen } from '../util/dom';
import { _ } from '../util/i18n';
import { jump_to_top } from '../util/scroll';
import { scaledown_images } from './images';
import { render_maps } from './maps';

interface ShareitboxOptions {
    id: string;
    url?: string;
    title?: string;
    reshareit?: boolean;
    width?: number | string;
    height?: number | string;
}

/** The sites the share box offers; you may overwrite them in user-scripts.js. */
export const DEFAULT_SHARING_SITES: GlsSharingSite[] = [
    {
        name: 'E-mail',
        href: 'mailto:?subject={URL}&body={TITLE}',
        className: 'email',
    },
    {
        name: 'Mastodon',
        // Mastodon's own page, which asks for the reader's server and remembers it.
        href: 'https://share.joinmastodon.org/#text={TITLE}%20{URL}',
        className: 'mastodon',
    },
    {
        name: 'Bluesky',
        href: 'https://bsky.app/intent/compose?text={TITLE}%20{URL}',
        className: 'bluesky',
    },
    {
        name: 'X',
        href: 'https://x.com/intent/tweet?text={TITLE}&url={URL}',
        className: 'x',
    },
    {
        // Facebook takes the title from the page's Open Graph tags.
        name: 'Facebook',
        href: 'https://www.facebook.com/sharer/sharer.php?u={URL}',
        className: 'facebook',
    },
    {
        name: 'Reddit',
        href: 'https://www.reddit.com/submit?url={URL}&title={TITLE}',
        className: 'reddit',
    },
];

export const share_state = {
    sites: [] as GlsSharingSite[],
};

/** Reposts an entry as a selfpost, after asking. */
export function reshare_entry(link: HTMLElement): boolean {
    if (!confirm(_('You are about to re-share this entry at your stream. Confirm?'))) {
        return false;
    }
    const as_me = !confirm(_('Keep the original author?'));
    const id = link.id.split('-')[1] as string;
    show_spinner(link);
    void post_text(config.baseurl + 'api/reshare', {
        entry: id,
        as_me: as_me ? 1 : 0,
    }).then((html) => {
        if (html === null) {
            return;
        }
        hide_spinner();
        Shareitbox.close();
        jump_to_top();
        document.getElementById('stream')?.insertAdjacentHTML('afterbegin', html);
        const first = document.querySelector('#stream article');
        render_maps(first);
        if (first) {
            scaledown_images(first.querySelectorAll('img'));
        }
    });
    return false;
}

function text_of(elements: NodeListOf<Element>): string {
    return Array.from(elements, (el) => el.textContent)
        .join('')
        .trim();
}

/** Opens the share box of the entry a share link belongs to. */
export function shareit_entry(link: HTMLElement): boolean {
    const that = (link.parentNode as HTMLElement).parentNode as HTMLElement;
    const id = link.id.split('-')[1] as string;
    const published = that.querySelectorAll('.entry-published a')[1];
    let url: string;
    if (that.classList.contains('private') && published) {
        url = published.getAttribute('href') as string;
    } else {
        url = that.querySelector('a[rel=bookmark]')?.getAttribute('href') as string;
        if (window.location.href.indexOf(url) !== -1) {
            url = window.location.href;
        } else {
            url = new URL(url, window.location.href).href;
        }
    }
    const titles = that.querySelectorAll('.entry-title');
    let title = text_of(
        titles.length ? titles : that.querySelectorAll('.entry-content'),
    );
    if (title.length > 137) {
        title = title.slice(0, 137) + '...';
    }
    Shareitbox.open({
        id: id,
        url: url,
        title: title,
        reshareit: link.classList.contains('reshareit'),
    });
    return false;
}

let sbox: HTMLDivElement | null = null;

function init(): HTMLDivElement {
    sbox ||= h('div', { id: 'shareitbox', style: { display: 'none' } });
    if (!sbox.isConnected) {
        document.body.appendChild(sbox);
    }
    return sbox;
}

/** A site in the share box: its icon and name, linked. */
function share_link(
    href: string,
    icon: HTMLElement | null,
    name: string,
): HTMLAnchorElement {
    return h('a', { href }, [icon, '\u00a0', name]);
}

function close_on_escape(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
        e.preventDefault();
        close();
    }
}

function open(opts: ShareitboxOptions): boolean {
    const box = init();
    const width = opts.width || 356;
    const height = opts.height;
    const url = opts.url || '';
    const title = opts.title || '';
    const reshareit = opts.reshareit || false;

    Overlay.enable(40);
    const o = h('div');
    // oxlint-disable-next-line typescript/no-for-in-array -- iterates as the jQuery script did
    for (const i in share_state.sites) {
        const s = share_state.sites[i] as GlsSharingSite;
        let href = s.href.replace('{URL}', encodeURIComponent(url));
        href = href.replace('{TITLE}', encodeURIComponent(title));

        let icon: HTMLElement | null = null;
        if (s.className) {
            icon = h('span', { className: 'share-' + s.className });
        } else if (s.icon) {
            icon = h('img', { src: s.icon, width: 16, height: 16 });
        }
        const link = share_link(href, icon, s.name);
        link.target = '_blank';
        o.appendChild(h('div', { className: 'item' }, [link]));
    }

    // Web Share API
    if ((navigator as Partial<Navigator>).share) {
        const link = share_link(
            '#',
            h('span', { className: 'share-webshare' }),
            'Web Share',
        );
        listen(link, 'click', function () {
            navigator.share({ title: title, url: url }).catch(() => {
                // Not allowed here, or cancelled.
            });
            return false;
        });
        o.appendChild(h('div', { className: 'item' }, [link]));
    }

    if (reshareit) {
        const reshare = h('a', { id: 'reshare-' + opts.id, href: '#' }, [
            _('Reshare it at your stream'),
        ]);
        listen(reshare, 'click', reshare_entry);
        box.appendChild(
            h('div', { className: 'reshare' }, [
                reshare,
                ' ' + _('or elsewhere:') + ' ',
            ]),
        );
    } else {
        box.appendChild(
            h('div', { className: 'reshare' }, [_('Share or bookmark this entry')]),
        );
    }
    box.appendChild(o);

    box.style.width = typeof width == 'number' ? width + 'px' : width;
    if (!height) {
        box.style.height = 'auto';
    } else {
        box.style.height = typeof height == 'number' ? height + 'px' : height;
    }
    box.style.position = 'absolute';
    box.style.display = 'block';
    MDOM.center(box, box.offsetWidth, box.offsetHeight);

    listen(document.getElementById('overlay'), 'click', close);
    document.addEventListener('keydown', close_on_escape);
    return false;
}

function close(): void {
    const box = init();
    document.removeEventListener('keydown', close_on_escape);
    box.style.display = 'none';
    box.replaceChildren();
    Overlay.disable();
}

export const Shareitbox = { init, open, close };
