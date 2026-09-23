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
import { Overlay } from '../ui/overlay';
import { hide_spinner, show_spinner } from '../ui/spinner';
import { DCE, MDOM } from '../util/dom';
import { _ } from '../util/i18n';
import { jump_to_top } from '../util/scroll';
import { scaledown_images } from './images';
import { render_map } from './maps';

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
        name: 'Twitter',
        href: 'https://twitter.com/?status={TITLE}:%20{URL}',
        className: 'twitter',
    },
    {
        name: 'Facebook',
        href: 'https://www.facebook.com/sharer.php?u={URL}&t={TITLE}',
        className: 'facebook',
    },
    {
        name: 'Reddit',
        href: 'https://reddit.com/submit?url={URL}&title={TITLE}',
        className: 'reddit',
    },
];

export const share_state = {
    sites: [] as GlsSharingSite[],
};

/** Reposts an entry as a selfpost, after asking. */
export function reshare_entry(this: HTMLElement): boolean {
    if (!confirm(_('You are about to re-share this entry at your stream. Confirm?'))) {
        return false;
    }
    const as_me = !confirm(_('Keep the original author?'));
    const id = this.id.split('-')[1] as string;
    show_spinner(this);
    $.post(
        config.baseurl + 'api/reshare',
        {
            entry: id,
            as_me: as_me ? 1 : 0,
        },
        function (html: string) {
            hide_spinner();
            Shareitbox.close();
            jump_to_top();
            $('#stream').prepend(html);
            $('#stream article:first a.map').each(render_map);
            scaledown_images('#stream article:first img');
        },
    );
    return false;
}

/** Opens the share box of the entry a share link belongs to. */
export function shareit_entry(this: HTMLElement): boolean {
    const that = (this.parentNode as HTMLElement).parentNode as HTMLElement;
    const id = this.id.split('-')[1] as string;
    const published = $('.entry-published a:eq(1)', that);
    let url: string;
    if ($(that).hasClass('private') && published.length) {
        url = published.attr('href') as string;
    } else {
        url = $('a[rel=bookmark]', that).attr('href') as string;
        if (window.location.href.indexOf(url) !== -1) {
            url = window.location.href;
        } else {
            url = 'http://' + window.location.host + url;
        }
    }
    const title_el = $('.entry-title', that);
    let title: string;
    if (title_el.length) {
        title = $.trim(title_el.text());
    } else {
        title = $.trim($('.entry-content', that).text());
    }
    if (title.length > 137) {
        title = title.substr(0, 137) + '...';
    }
    Shareitbox.open({
        id: id,
        url: url,
        title: title,
        reshareit: $(this).hasClass('reshareit'),
    });
    return false;
}

let initied = false;
let sbox: HTMLDivElement | null = null;

function init(): void {
    if (initied) {
        return;
    }
    sbox = document.createElement('div');
    sbox.id = 'shareitbox';
    sbox.style.display = 'none';
    document.body.appendChild(sbox);
    initied = true;
}

function open(opts: ShareitboxOptions): boolean {
    init();
    const box = sbox as HTMLDivElement;
    const width = opts.width || 356;
    const height = opts.height;
    const url = opts.url || '';
    const title = opts.title || '';
    const reshareit = opts.reshareit || false;

    Overlay.enable(40);
    const o = DCE('div');
    // oxlint-disable-next-line typescript/no-for-in-array -- iterates as the jQuery script did
    for (const i in share_state.sites) {
        const s = share_state.sites[i] as GlsSharingSite;
        let href = s.href.replace('{URL}', encodeURIComponent(url));
        href = href.replace('{TITLE}', encodeURIComponent(title));

        let img;
        if (s.className) {
            img = DCE('span', {
                className: 'share-' + s.className,
            });
        } else if (s.icon) {
            img = DCE('img', {
                src: s.icon,
                width: 16,
                height: 16,
            });
        }

        o.appendChild(
            DCE(
                'div',
                {
                    className: 'item',
                },
                [
                    DCE(
                        'a',
                        {
                            href: href,
                            target: '_blank',
                        },
                        [
                            img,
                            document.createTextNode(String.fromCharCode(160)),
                            document.createTextNode(s.name),
                        ],
                    ),
                ],
            ),
        );
    }

    // Web Share API
    if ((navigator as Partial<Navigator>).share) {
        const img = DCE('span', {
            className: 'share-webshare',
        });
        o.appendChild(
            DCE(
                'div',
                {
                    className: 'item',
                },
                [
                    DCE(
                        'a',
                        {
                            href: '#',
                            onclick: function () {
                                try {
                                    void navigator.share({
                                        title: title,
                                        url: url,
                                    });
                                } catch {
                                    // Not allowed here, or cancelled.
                                }
                            },
                        },
                        [
                            img,
                            document.createTextNode(String.fromCharCode(160)),
                            document.createTextNode('Web Share'),
                        ],
                    ),
                ],
            ),
        );
    }

    if (reshareit) {
        box.appendChild(
            DCE(
                'div',
                {
                    className: 'reshare',
                },
                [
                    DCE(
                        'a',
                        {
                            id: 'reshare-' + opts.id,
                            href: '#',
                            onclick: reshare_entry,
                        },
                        [_('Reshare it at your stream')],
                    ),
                    document.createTextNode(' ' + _('or elsewhere:') + ' '),
                ],
            ),
        );
    } else {
        box.appendChild(
            DCE(
                'div',
                {
                    className: 'reshare',
                },
                [_('Share or bookmark this entry')],
            ),
        );
    }
    box.appendChild(o);

    if (typeof width == 'number') {
        box.style.width = width + 'px';
    } else {
        box.style.width = width;
    }
    if (!height) {
        box.style.height = 'auto';
    } else if (typeof height == 'number') {
        box.style.height = height + 'px';
    } else {
        box.style.height = height;
    }
    box.style.position = 'absolute';
    box.style.display = 'block';
    MDOM.center(box, $(box).outerWidth(), $(box).outerHeight());

    $('#overlay').click(close);
    document.onkeydown = function (e) {
        let code;
        if (!e) {
            e = window.event as KeyboardEvent;
        }
        if (e.keyCode) {
            code = e.keyCode;
        } else if (e.which) {
            code = e.which;
        }
        if (code === 27) {
            /* escape */
            close();
            return false;
        }
        return true;
    };

    return false;
}

function close(): void {
    const box = sbox as HTMLDivElement;
    document.onkeydown = null;
    box.style.display = 'none';
    box.innerHTML = '';
    Overlay.disable();
}

export const Shareitbox = { init, open, close };
