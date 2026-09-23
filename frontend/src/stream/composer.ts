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

import type { SelfpostsClass } from '../api-types';
import { config } from '../config';
import { hide_spinner, show_spinner } from '../ui/spinner';
import { scroll_to_top } from '../util/scroll';
import { $M } from './entry-actions';
import { scaledown_images } from './images';
import { render_map } from './maps';

/** The selfpost composer at the top of the stream. */
export const composer = {
    /** The rich editor, when the page loaded Quill. */
    quill: undefined as QuillEditor | undefined,
    /** The selfposts classes from api/gsc, once loaded. */
    gsc_load: false as false | SelfpostsClass[],
    /** Whether the class select has its options. */
    gsc_done: false,
    /** The entry being edited, or 0 for a new post. */
    editor_id: 0 as number | string,
};

function set_share_expanded(expanded: boolean): void {
    $('#share > form').toggle(expanded);
    $('#share').toggleClass('share-collapsed', !expanded);
}

/** Opens or closes the composer. */
export function open_sharing(): boolean {
    composer.editor_id = 0;
    $('#update').hide();
    $('#post').show();
    const fieldset = $('#share .fieldset');
    const expanding = !fieldset.is(':visible');
    set_share_expanded(expanding);
    fieldset.stop(true, true)[expanding ? 'slideDown' : 'slideUp'](function () {
        if (expanding) {
            if (composer.quill) {
                composer.quill.focus();
            } else {
                $('#status').focus();
            }
            if (!composer.gsc_done) {
                get_selfposts_classes();
            }
        } else {
            set_share_expanded(false);
        }
    });
    return false;
}

function show_selfposts_classes(): void {
    const sc = $('#status-class').get(0) as HTMLSelectElement;
    const classes = composer.gsc_load as SelfpostsClass[];
    // oxlint-disable-next-line typescript/no-for-in-array -- iterates as the jQuery script did
    for (const i in classes) {
        const item = classes[i] as SelfpostsClass;
        sc.options[sc.options.length] = new Option(item['cls'], String(item['id']));
    }
    composer.gsc_done = true;
}

function get_selfposts_classes(): void {
    if (!composer.gsc_load) {
        $.getJSON(config.baseurl + 'api/gsc', function (json: SelfpostsClass[]) {
            composer.gsc_load = json;
            show_selfposts_classes();
        });
    } else {
        show_selfposts_classes();
    }
}

export function open_more_sharing_options(this: HTMLElement): boolean {
    $(this).hide();
    $('#more-sharing-options').fadeIn();
    return false;
}

/** Whether Quill's HTML holds neither text nor a picture. */
export function is_quill_empty(value: string): boolean {
    return (
        value.replace(/<(.|\n)*?>/g, '').trim().length === 0 &&
        value.indexOf('<img') === -1
    );
}

/** Posts the composer's content, or saves the entry being edited. */
export function share(this: HTMLElement): boolean {
    const docs = $<HTMLInputElement>('input[name=docs]');
    if (docs.length) {
        const files = (docs.get(0) as HTMLInputElement).files;
        if (files && files.length) {
            return true;
        }
    }
    const postButton = $(this);
    postButton.attr('disabled', 'disabled');
    let content: string;
    let isEmptyContent = false;
    if (composer.quill) {
        content = composer.quill.root.innerHTML;
        isEmptyContent = is_quill_empty(content);
    } else {
        content = $('#status').val() as string;
        isEmptyContent = $.trim(content) === '';
    }
    if (!isEmptyContent) {
        show_spinner(this);
        if (composer.editor_id) {
            $.post(
                config.baseurl + 'api/putcontent',
                {
                    entry: composer.editor_id,
                    content: content,
                },
                function () {
                    hide_spinner();
                    postButton.removeAttr('disabled');
                },
            );
        } else {
            $.post(
                config.baseurl + 'api/share',
                {
                    sid: $('#status-class').val(),
                    content: content,
                    draft: $('#draft').prop('checked') ? 1 : 0,
                    friends_only: $('#friends-only').prop('checked') ? 1 : 0,
                },
                function (html: string) {
                    hide_spinner();
                    $('#stream article.hentry').first().before(html);
                    $('#stream article:first a.map').each(render_map);
                    postButton.removeAttr('disabled');
                    $('#share .fieldset').slideUp(function () {
                        set_share_expanded(false);
                    });
                    editor_clear();
                    scaledown_images('#stream article:first img');
                },
            );
        }
    } else {
        postButton.removeAttr('disabled');
    }
    return false;
}

function editor_clear(): void {
    if (composer.quill) {
        composer.quill.root.innerHTML = '';
    } else {
        $('#status').val('');
    }
}

/** Opens an entry's stored HTML in the composer for editing. */
export function edit_entry(this: HTMLElement, e?: JQuery.TriggeredEvent): void {
    if (e) {
        e.preventDefault();
    }
    $('#status-editor').css('height', '400px');
    set_share_expanded(true);
    $('#share > form').show();
    $('#share .fieldset').show();
    if (!composer.gsc_done) {
        get_selfposts_classes();
    }

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
            composer.editor_id = id;
            (composer.quill as QuillEditor).clipboard.dangerouslyPasteHTML(html);
            $('#update,#post').toggle();
            scroll_to_top();
        },
    );
}

/** Replaces the plain textarea with Quill, when the page loaded it. */
export function init_quill(): void {
    if (window.Quill) {
        $('#status').hide();
        const qblock = Quill.import('blots/block');
        qblock.tagName = 'div';
        Quill.register(qblock);
        composer.quill = new Quill('#status-editor', {
            modules: {
                toolbar: {
                    container: [
                        [{ font: [] }, { size: [] }],
                        ['bold', 'italic', 'underline', 'strike'],
                        [{ color: [] }, { background: [] }],
                        [{ header: '1' }, { header: '2' }, 'blockquote', 'code-block'],
                        [
                            { list: 'ordered' },
                            { list: 'bullet' },
                            { indent: '-1' },
                            { indent: '+1' },
                        ],
                        ['direction', { align: [] }],
                        ['link', 'image', 'video'],
                        ['clean'],
                    ],
                },
            },
            theme: 'snow',
        });
    }
}

/** The PWA share target: /share?title=&text=&url= opens a filled composer. */
export function init_share_target(): void {
    const parsedUrl = new URL(window.location.href);
    if (parsedUrl.pathname.endsWith('/share')) {
        open_sharing();
        const title = parsedUrl.searchParams.get('title');
        const text = parsedUrl.searchParams.get('text');
        const url = parsedUrl.searchParams.get('url');
        let body = '';
        if (title) {
            body += title + '<br>';
        }
        if (text) {
            body += text + '<br>';
        }
        if (url) {
            body += url + '<br>';
        }
        if (composer.quill) {
            composer.quill.clipboard.dangerouslyPasteHTML(body);
        } else {
            $('#status').val(body.replace(/<br>/g, '\n'));
        }
    }
}
