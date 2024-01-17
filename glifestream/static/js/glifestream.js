/*
 *  gLifestream Copyright (C) 2009-2024 Wojciech Polak
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

/*jshint indent: 4, white: true, browser: true */
/*global $, Quill, settings, gettext_msg, stream_data */

(function() {
    function parse_id(id) {
        const p = id.indexOf('-');
        if (p === -1) {
            return [id];
        }
        return [id.substring(0, p), id.substr(p + 1)];
    }

    function play_video() {
        let a = parse_id($(this).data('id') || this.id);
        let type = a[0];
        let id = a[1];

        let embed = '';
        if (type in video_embeds) {
            embed = video_embeds[type].replace(/{ID}/g, id);
        }
        else {
            return true;
        }

        $('.playbutton', this).removeClass('playbutton').addClass('stopbutton');
        $VC(this).after('<div class="player video ' +
                        type + '">' + embed + '</div>');
        $('a', this).blur();
        scroll_to_element(this);
        return false;
    }

    function stop_video() {
        $('.player', $VC(this).parent()).remove();
        $('.stopbutton', this).removeClass('stopbutton').addClass('playbutton');
        $('a', this).blur();
        return false;
    }

    function toggle_video() {
        let $this = $(this);
        if (!$this.hasClass('video-inline')) {
            if ($('.playbutton', this).length) {
                play_video.call(this);
            }
            else {
                stop_video.call(this);
            }
        }
        else {
            if (!$this.data('play')) {
                $this.data('play', true);
                play_video.call(this);
            }
            else {
                stop_video.call(this);
                $this.data('play', false);
            }
        }
        return false;
    }

    /* find VC block */
    function $VC(obj) {
        if (obj.parentNode.tagName === 'TD') {
            obj = obj.parentNode.parentNode.parentNode.parentNode;
            if (obj.className === 'vc') {
                return $(obj);
            }
        }
        return $(obj);
    }

    function play_audio(e) {
        if (e.which && e.which !== 1) {
            return false;
        }
        let a = parse_id($(this).data('id') || this.id);
        let type = a[0];
        $('a', this).blur();

        if ($('.player', this.parentNode).length) {
            $('.player', this.parentNode).remove();
            return false;
        }

        let embed;
        if (type === 'audio') {
            embed = '<audio src="' + $('a', this).attr('href') +
                '" controls="true">' + _('Your browser does not support it.') +
                '</audio>';
        }
        else if (type in audio_embeds) {
            embed = audio_embeds[type];
        }
        else if (type === 'thesixtyone') {
            return false; // prevent navigating to a defunct site
        }
        else {
            return true;
        }

        let id;
        if (type === 'thesixtyone') {
            let data = a[1].split('-');
            let artist = data[0];
            id = data[1];
            embed = embed.replace('{ARTIST}', artist);
        }
        else if (type === 'mp3') {
            id = $('a', this).attr('href');
        }
        else {
            id = a[1];
        }

        embed = embed.replace(/{ID}/g, id);

        $('.player').remove();
        $(this.parentNode).append('<div class="player audio">' +
                                  embed + '</div>');
        if (type === 'audio') {
            let $au = $(this.parentNode).find('audio');
            if ($au.length) {
                $au[0].play();
            }
        }
        return false;
    }

    /* find menu */
    function $M(entry) {
        return $('.entry-controls-switch',
                 entry.parentNode.parentNode.parentNode)[0];
    }

    function load_entries() {
        const that = this;
        if (that.busy) {
            return false;
        }
        that.busy = true;
        if (articles.length >= continuous_reading) {
            return follow_href.call(this);
        }
        show_spinner(this);
        let url = this.href;
        url += (url.indexOf('?') !== -1) ? '&' : '?';
        url += 'format=html-pure';
        $.getJSON(url, function(json) {
            hide_spinner();
            that.busy = false;
            let num = articles.length;
            $(articles[num - 1]).after(json.stream);
            nav_next.each(function() {
                let s = this.href.indexOf('start=');
                if (s !== -1 && json.next) {
                    this.href = this.href.substring(0, s + 6) + json.next;
                }
                else {
                    s = this.href.indexOf('page=');
                    if (s !== -1 && json.next) {
                        this.href = this.href.substring(0, s + 5) + json.next;
                    }
                    else {
                        $(this).remove();
                    }
                }
            });
            articles = $('#stream article');
            num = articles.length - num;
            const latest = $('#stream article').slice(-num);
            Graybox.scan(latest);
            alter_html(latest);
            $('a.map', latest).each(render_map);
            scaledown_images($('img', latest));
            scroll_to_element(latest[0], 25);
        });
        return false;
    }

    function hide_entry(e) {
        if (e) {
            e.preventDefault();
        }
        if (($('span.favorite', $M(this).parentNode).length)) {
            alert(_('Unfavorite this entry before hiding it.'));
            return false;
        }
        const id = this.id.split('-')[1];
        show_spinner($M(this));
        $.post(baseurl + 'api/hide', {
            entry: id
        }, function() {
            hide_spinner();
            $('#entry-' + id).fadeOut('normal', function() {
                $(this).after('<div id="hidden-' + id + '" class="entry-hidden"><em>' + _('Entry hidden') + '</em> - <a href="#" onclick="return gls.unhide_entry.call(this)">' + _('Undo') + '</a></div>');
            });
        });
    }

    function unhide_entry() {
        const id = this.parentNode.id.split('-')[1];
        show_spinner(this);
        $.post(baseurl + 'api/unhide', {
            entry: id
        }, function() {
            hide_spinner();
            $('#hidden-' + id).remove();
            $('#entry-' + id).fadeIn();
        });
        return false;
    }

    function favorite_entry(e) {
        if (e) {
            e.preventDefault();
        }
        const that = this;
        const id = this.id.split('-')[1];
        show_spinner($M(this));
        if (!$(this).hasClass('fav')) {
            $.post(baseurl + 'api/favorite', {
                entry: id
            }, function() {
                hide_spinner();
                $($M(that)).before('<span class="favorite"></span>');
                $(that).addClass('fav').html(_('Unfavorite'));
            });
        }
        else {
            $.post(baseurl + 'api/unfavorite', {
                entry: id
            }, function() {
                hide_spinner();
                $('span.favorite', $M(that).parentNode).remove();
                $(that).removeClass('fav').html(_('Favorite'));
            });
        }
    }

    function reshare_entry() {
        if (!confirm(_('You are about to re-share this entry at your stream. Confirm?'))) {
            return false;
        }
        const as_me = !confirm(_('Keep the original author?'));
        const id = this.id.split('-')[1];
        show_spinner(this);
        $.post(baseurl + 'api/reshare', {
            entry: id,
            as_me: as_me ? 1 : 0
        }, function(html) {
            hide_spinner();
            Shareitbox.close();
            jump_to_top();
            $('#stream').prepend(html);
            $('#stream article:first a.map').each(render_map);
            scaledown_images('#stream article:first img');
        });
        return false;
    }

    function shareit_entry() {
        const that = this.parentNode.parentNode;
        const id = this.id.split('-')[1];
        let url = $('.entry-published a:eq(1)', that);
        if ($(that).hasClass('private') && url.length) {
            url = url.attr('href');
        }
        else {
            url = $('a[rel=bookmark]', that).attr('href');
            if (window.location.href.indexOf(url) !== -1) {
                url = window.location.href;
            }
            else {
                url = 'http://' + window.location.host + url;
            }
        }
        let title = $('.entry-title', that);
        if (title.length) {
            title = strip_tags_trim(title.html());
        }
        else {
            title = strip_tags_trim($('.entry-content', that).html());
        }
        if (title.length > 137) {
            title = title.substr(0, 137) + '...';
        }
        Shareitbox.open({
            id: id,
            url: url,
            title: title,
            reshareit: $(this).hasClass('reshareit')
        });
        return false;
    }

    function edit_entry(e) {
        if (e) {
            e.preventDefault();
        }
        $('#status-editor').css('height', '400px');
        $('#share .fieldset').show();
        if (!gsc_done) {
            get_selfposts_classes();
        }

        const id = this.id.split('-')[1];
        show_spinner($M(this));
        $.post(baseurl + 'api/getcontent', {
            entry: id,
            raw: 1
        }, function(html) {
            hide_spinner();
            editor_id = id;
            quill.clipboard.dangerouslyPasteHTML(html);
            $('#update,#post').toggle();
            scroll_to_top();
        });
    }

    function edit_raw_entry(e) {
        if (e) {
            e.preventDefault();
        }
        const that = this;
        const id = this.id.split('-')[1];
        show_spinner($M(this));
        $.post(baseurl + 'api/getcontent', {
            entry: id,
            raw: 1
        }, function(html) {
            hide_spinner();
            const ec = $(that).closest('article').find('.entry-content');
            const editor = $('#entry-editor');
            $('#edited-content').val(html);
            ec.after(editor);
            editor.fadeIn('normal', function() {
                scroll_to_element(editor, 400);
            });
        });
    }

    function editor_handler() {
        const op = this.getAttribute('name');
        if (op === 'cancel') {
            $('#entry-editor').fadeOut();
        }
        else if (op === 'save') {
            show_spinner(this);
            const article = $(this).closest('article').get(0);
            const id = parse_id(article.id)[1];
            $.post(baseurl + 'api/putcontent', {
                entry: id,
                content: $('#edited-content').val()
            }, function(html) {
                hide_spinner();
                $('#entry-' + id + ' .entry-content').html(html);
            });
        }
    }

    function toggle_reblogs() {
        const cookie_name = 'gls-reblogs';
        let val = read_cookie(cookie_name);
        val = (!+val) ? '1' : '0';
        write_cookie(cookie_name, val, 365, baseurl);
        window.location.reload();
        return false;
    }

    function change_theme() {
        const cookie_name = 'gls-theme';
        let cs = read_cookie(cookie_name);
        let idx = $.inArray(cs, settings.themes);

        if (!cs || idx === -1) {
            idx = 0;
            cs = settings.themes[idx];
        }
        if (idx < settings.themes.length - 1) {
            idx++;
        }
        else {
            idx = 0;
        }
        cs = settings.themes[idx];
        write_cookie(cookie_name, cs, 365, baseurl);
        jump_to_top();
        window.location.reload();
        return false;
    }

    function show_spinner(el) {
        if (el.blur) {
            el.blur();
        }
        $(el).after('<span id="spinner"></span>');
    }

    function hide_spinner() {
        $('#spinner').remove();
    }

    function read_cookie(name) {
        const nameEq = name + '=';
        const ca = document.cookie.split(';');
        for (let i = 0; i < ca.length; i++) {
            let c = ca[i];
            while (c.charAt(0) === ' ') {
                c = c.substring(1, c.length);
            }
            if (c.indexOf(nameEq) === 0) {
                return c.substring(nameEq.length, c.length);
            }
        }
        return null;
    }

    function write_cookie(name, value, expire_days, path) {
        const date = new Date();
        date.setTime(date.getTime() + (expire_days * 86400000));
        const expires = '; expires=' + date.toGMTString();
        document.cookie = name + '=' + value + expires +
            '; path=' + path;
    }

    function alter_html(ctx) {
        $('.thumbnails a', ctx)
            .each(function() {
                let id = '';
                try {
                    if (this.href.indexOf('https://www.youtube.com/watch') === 0) {
                        id = 'youtube-' + this.href.substr(32);
                    }
                    else if (this.href.indexOf('https://vimeo.com/') === 0) {
                        id = 'vimeo-' + this.href.substr(18);
                    }
                    else if (this.href.indexOf('http://www.youtube.com/watch') === 0) {
                        id = 'youtube-' + this.href.substr(31);
                    }
                    else if (this.href.indexOf('http://vimeo.com/') === 0) {
                        id = 'vimeo-' + this.href.substr(17);
                    }
                    if (id) {
                        $(this).wrap('<div id="' + id + '" class="play-video"></div>');
                        $(this).after('<div class="playbutton"></div>');
                    }
                }
                catch (e) {}
            });

        $('.files a[href$=".mp3"]', ctx).wrap('<span data-id="audio-x" class="play-audio"></span>');
        $('.files a[href$=".ogg"]', ctx).wrap('<span data-id="audio-x" class="play-audio"></span>');

        if (typeof window.user_alter_html == 'function') {
            window.user_alter_html(ctx);
        }
    }

    let gsc_load = false;
    let gsc_done = false;
    let editor_id = 0;

    function open_sharing() {
        editor_id = 0;
        $('#update').hide();
        $('#post').show();
        $('#share .fieldset').toggle(function() {
            if (quill) {
                quill.focus();
            }
            else {
                $('#status').focus();
            }
            if (!gsc_done) {
                get_selfposts_classes();
            }
        });
        return false;
    }

    function show_selfposts_classes() {
        const sc = $('#status-class').get(0);
        for (let i in gsc_load) {
            sc.options[sc.options.length] = new Option(gsc_load[i]['cls'],
                                                       gsc_load[i]['id']);
        }
        gsc_done = true;
    }

    function get_selfposts_classes() {
        if (!gsc_load) {
            $.getJSON(baseurl + 'api/gsc', function(json) {
                gsc_load = json;
                show_selfposts_classes();
            });
        }
        else {
            show_selfposts_classes();
        }
    }

    function open_more_sharing_options() {
        $(this).hide();
        $('#more-sharing-options').fadeIn();
        return false;
    }

    function is_quill_empty(value) {
        return value.replace(/<(.|\n)*?>/g, '').trim().length === 0 &&
            value.indexOf('<img') === -1;
    }

    function share() {
        const docs = $('input[name=docs]');
        if (docs.length && docs.get(0).files && docs.get(0).files.length) {
            return true;
        }
        const postButton = $(this);
        postButton.attr('disabled', 'disabled');
        let content;
        let isEmptyContent = false;
        if (quill) {
            content = quill.root.innerHTML;
            isEmptyContent = is_quill_empty(content);
        }
        else {
            content = $('#status').val();
            isEmptyContent = $.trim(content) === '';
        }
        if (!isEmptyContent) {
            show_spinner(this);
            if (editor_id) {
                $.post(baseurl + 'api/putcontent', {
                    entry: editor_id,
                    content: content
                }, function() {
                    hide_spinner();
                    postButton.removeAttr('disabled');
                });
            }
            else {
                $.post(baseurl + 'api/share', {
                    sid: $('#status-class').val(),
                    content: content,
                    draft: $('#draft').attr('checked') ? 1 : 0,
                    friends_only: $('#friends-only').attr('checked') ? 1 : 0
                }, function (html) {
                    hide_spinner();
                    $('#stream article.hentry').first().before(html);
                    $('#stream article:first a.map').each(render_map);
                    postButton.removeAttr('disabled');
                    $('#share .fieldset').slideUp();
                    editor_clear();
                    scaledown_images('#stream article:first img');
                });
            }
        }
        else {
            postButton.removeAttr('disabled');
        }
        return false;
    }

    function editor_clear() {
        if (quill) {
            quill.root.innerHTML = '';
        }
        else {
            $('#status').val('');
        }
    }

    function get_map_embed(lat, lng) {
        if (settings.maps_engine === 'google') {
            return '<img src="https://maps.googleapis.com/maps/api/staticmap?sensor=false&zoom=12&size=175x120&markers=' + lat + ',' + lng + '" alt="Map" width="175" height="120" />';
        }
        const boundingBox = calculateBoundingBox(lat, lng, 10);
        const bbox = convertToOSMBbox(boundingBox);

        return '<iframe width="100%" height="200" ' +
            'src="https://www.openstreetmap.org/export/embed.html?layer=mapnik' +
            '&bbox=' + bbox +
            '&marker=' + lat + ',' + lng + '" ' +
            'style="border: 1px solid black"></iframe>' +
            '<br/>' +
            '<small>' +
            '<a href="https://www.openstreetmap.org/?mlat=' +
            lat + '&mlon=' + lng + '#map=10/' + lat + '/' + lng +
            '" target="_blank">View Larger Map</a>' +
            '</small>';
    }

    function render_map() {
        const lat = $('.latitude', this).html();
        const lng = $('.longitude', this).html();
        this.target = '_blank';
        this.parentNode.style.paddingLeft = 0;
        this.parentNode.style.background = 'none';
        $(this).html(get_map_embed(lat, lng));
    }

    function show_map() {
        this.blur();
        if (this.folded) {
            return true;
        }
        let lat = $('.latitude', this).html();
        let lng = $('.longitude', this).html();
        this.target = '_blank';

        if (settings.maps_engine === 'google') {
            this.href = 'https://maps.google.com/?q=' + lat + ',' + lng;
        }
        else {
            this.href = 'https://www.openstreetmap.org/?mlat=' +
            lat + '&mlon=' + lng + '#map=10/' + lat + '/' + lng;
        }

        const p = this.parentNode;
        $('a', p).html(get_map_embed(lat, lng));
        $(p).css('paddingLeft', '0');
        this.folded = true;
        return false;
    }

    function calculateBoundingBox(lat, lon, radiusKm) {
        const earthRadiusKm = 6371;
        const latRad = (lat * Math.PI) / 180;
        const lonRad = (lon * Math.PI) / 180;
        const angularDistance = radiusKm / earthRadiusKm;
        const latDiff = (angularDistance * 180) / Math.PI;
        const lonDiff = (angularDistance * 180) / (Math.PI * Math.cos(latRad));
        const swLat = +lat - +latDiff;
        const swLon = +lon - +lonDiff;
        const neLat = +lat + +latDiff;
        const neLon = +lon + +lonDiff;
        return {
            southwest: {lat: swLat, lon: swLon},
            northeast: {lat: neLat, lon: neLon},
        };
    }

    function convertToOSMBbox(boundingBox) {
        const { southwest, northeast } = boundingBox;
        return `${southwest.lon.toFixed(7)},${southwest.lat.toFixed(7)},` +
            `${northeast.lon.toFixed(7)},${northeast.lat.toFixed(7)}`;
    }

    function expand_content() {
        const that = this;
        const article = this.parentNode.parentNode;
        if (article.content_loaded) {
            if (article.content_expanded) {
                $('div.entry-content', article).slideUp();
                article.content_expanded = false;
            }
            else {
                $('div.entry-content', article).slideDown();
                article.content_expanded = true;
            }
        }
        else {
            const id = parse_id(article.id)[1];
            show_spinner(this);
            $.post(baseurl + 'api/getcontent', {
                entry: id
            }, function(html) {
                hide_spinner();
                $('div.entry-content', article).html(html).slideDown();
                article.content_loaded = true;
                article.content_expanded = true;
                scaledown_images($('img', article));
            });
        }
        return false;
    }

    let eco = null;

    function show_menu_controls() {
        hide_menu_controls();
        const that = this;
        const s = $('.entry-controls', this.parentNode);
        const pos = $(this).position();
        s.addClass('menu-expanded')
            .css({
                top: pos.top + 17,
                left: pos.left
            }).show();
        eco = s[0];
        document.onclick = hide_menu_controls;

        const y_bottom = pos.top + s.height();
        const y_diff = y_bottom - $(window).height() - $(document).scrollTop();
        if (y_diff > -20) {
            s.css('top', (pos.top - y_diff - 15) + 'px');
        }
        return false;
    }

    function hide_menu_controls() {
        if (eco) {
            $(eco).hide().removeClass('menu-expanded');
        }
        document.onclick = null;
    }

    function scaledown_images(sel) {
        const maxWidth = $('#stream').width() - 80;
        $(sel || '#stream img').each(function() {
            if (this.complete) {
                if (this.width > maxWidth) {
                    this.width = maxWidth;
                    if (this.style.width) {
                        const p = maxWidth * 100 / parseInt(this.style.width, 10);
                        this.style.width = maxWidth + 'px';
                        this.style.height = (this.height * p / 100) + 'px';
                    }
                }
            }
            else {
                this.onload = function() {
                    if (this.width > maxWidth) {
                        this.width = maxWidth;
                        if (this.style.width) {
                            const p = maxWidth * 100 / parseInt(this.style.width, 10);
                            this.style.width = maxWidth + 'px';
                            this.style.height = (this.height * p / 100) + 'px';
                        }
                    }
                    this.onload = null;
                };
            }
        });
    }

    let articles = [];
    let current_article = -1;

    function kshortcuts(e) {
        if (quill && quill.hasFocus()) {
            return;
        }
        let code, ent;
        if (!e) {
            e = window.event;
        }
        if (e.keyCode) {
            code = e.keyCode;
        }
        else if (e.which) {
            code = e.which;
        }
        if (e.ctrlKey || e.metaKey || e.altKey) {
            return true;
        }

        switch (code) {
        case 97:
            /* a */
            open_sharing();
            break;
        case 106:
            /* j */
            if ((current_article + 1) === articles.length) {
                nav_next.trigger('click');
            }
            else {
                highlight_article(articles[++current_article]);
            }
            break;
        case 107:
            /* k */
            if ((current_article - 1) < 0) {
                const prev = $('#stream a.prev');
                if (prev.length) {
                    window.location = prev.attr('href');
                }
            }
            else {
                highlight_article(articles[--current_article]);
            }
            break;
        case 102:
            /* f */
            ent = articles[current_article];
            if (ent) {
                const c = $('span.favorite-control', ent);
                if (c.length) {
                    favorite_entry.call(c[0]);
                }
            }
            break;
        case 104:
            /* h */
            ent = articles[current_article];
            if (ent) {
                const id = ent.id.split('-')[1];
                let c = $('#hidden-' + id + ' a');
                if (c.length) {
                    unhide_entry.call(c[0]);
                }
                else {
                    c = $('span.hide-control', ent);
                    if (c.length) {
                        hide_entry.call(c[0]);
                    }
                }
            }
            break;
        }
    }

    function highlight_article(article) {
        $('a:first', article).focus().blur();
        articles.removeClass('entry-highlight');
        $(article).addClass('entry-highlight');
        scroll_to_element(article, 24);
    }

    function scroll_to_element(t, offset) {
        offset = offset || 16;
        const toffset = $(t).offset().top - offset;
        $('html,body').animate({
            scrollTop: toffset
        }, 200);
    }

    function scroll_to_top() {
        $('html, body').animate({scrollTop: 0}, 'fast');
    }

    function jump_to_top() {
        if (document.body && document.body.scrollTop) {
            document.body.scrollTop = 0;
        }
        else if (document.documentElement && document.documentElement.scrollTop) {
            document.documentElement.scrollTop = 0;
        }
    }

    function gen_archive_calendar(year) {
        if (typeof stream_data === 'undefined') {
            return;
        }
        year = year || stream_data.view_date.split('/')[0];
        let month = 1;
        let cal = '<table>';
        cal += '<tr><th colspan="3">' +
            '<a href="#" class="prev">&nbsp;</a>';
        cal += '<span class="year">' + year + '</span> ';
        if (parseInt(year, 10) < stream_data.year_now) {
            cal += '<a href="#" class="next">&nbsp;</a>';
        }
        else {
            cal += '<span class="next-disabled">&nbsp;</span>';
        }
        cal += '</th></tr>';
        for (let row = 0; row < 4; row++) {
            cal += '<tr>';
            for (let col = 0; col < 3; col++, month++) {
                let d = year + '/' + pad(month, 2);
                let u = d === stream_data.view_date ? ' class="view-month"' : '';
                if ($.inArray(d, stream_data.archives) !== -1) {
                    const ctx = stream_data.ctx !== '' ? stream_data.ctx + '/' : '';
                    cal += '<td> <a href="' + settings.baseurl + ctx +
                        d + '/" rel="nofollow"' + u + '>' +
                        stream_data.month_names[month - 1] + '</a></td>';
                }
                else {
                    cal += '<td> ' + stream_data.month_names[month - 1] + '</td>';
                }
            }
            cal += '</tr>';
        }
        cal += '</table>';
        $('#calendar').html(cal);
    }

    function ajax_error() {
        alert(_('Communication Error. Try again.'));
        hide_spinner();
    }

    function gettext(msg) {
        if (typeof gettext_msg !== 'undefined' && gettext_msg[msg]) {
            return gettext_msg[msg];
        }
        return msg;
    }

    function _(msg) {
        return gettext(msg);
    }

    function es(ns, p) {
        const t = ns.split(/\./);
        let win = window;
        for (let i = 0; i < t.length - 1; i++) {
            if (typeof win[t[i]] == 'undefined') {
                win[t[i]] = {};
            }
            win = win[t[i]];
        }
        win[t[t.length - 1]] = p;
    }

    es('gls.unhide_entry', unhide_entry);
    $.ajaxSetup({
        error: ajax_error
    });
    let baseurl = '/';
    let continuous_reading = 300;
    let social_sharing_sites = [];
    let nav_next = null;
    let quill;

    $(document).ready(function() {
        baseurl = settings.baseurl;

        if (document.getElementById('settings')) {
            init_settings();
            return;
        }

        Graybox.scan();
        const stream = $('#stream').get(0);
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

        $('#sidebar-toggle').click(function() {
            $('#sidebar').toggleClass('expanded');
            $('i', this).toggleClass('fa-chevron-up fa-chevron-down');
        });

        $('#toggle-reblogs').click(toggle_reblogs);
        $('#change-theme').click(change_theme);
        $('div.lists select').change(function() {
            if (this.value !== '') {
                window.location = baseurl + 'list/' + this.value + '/';
            }
        });
        $(document).on('click', '#entry-editor input[type=button]', editor_handler);

        gen_archive_calendar();
        $(document).on('click', '#calendar a.prev', function() {
            const year = parseInt($('#calendar .year').html(), 10);
            gen_archive_calendar(year - 1);
            return false;
        });
        $(document).on('click', '#calendar a.next', function() {
            const year = parseInt($('#calendar .year').html(), 10);
            gen_archive_calendar(year + 1);
            return false;
        });

        scaledown_images();

        articles = $('article', stream);
        nav_next = $('nav a.next', stream);
        document.onkeypress = kshortcuts;

        $('span.play-audio', stream).each(function() {
            this.title = _('Click and Listen');
        });

        $('#status, #edited-content, form input[type=search]').
            focus(function() {
                document.onkeypress = null;
            }).
            blur(function() {
                document.onkeypress = kshortcuts;
            });

        $('form[name=searchform]').submit(function() {
            const s = $('input[name=s]').get(0);
            if (s && s.value !== '' && s.value !== s.PLACEHOLDER) {
                return true;
            }
            return false;
        });
        $('#search-submit').click(function() {
            $('form[name=searchform]').submit();
        });
        set_placeholder($('input[placeholder]'));

        $('#ashare').click(open_sharing);
        $('#expand-sharing').click(open_more_sharing_options);
        $('#update, #post').click(share);

        if (typeof window.continuous_reading !== 'undefined') {
            continuous_reading = parseInt(window.continuous_reading, 10);
        }
        nav_next.click(continuous_reading ? load_entries : follow_href);

        if (window.Quill) {
            $('#status').hide();
            const qblock = Quill.import('blots/block');
            qblock.tagName = 'div';
            Quill.register(qblock);
            quill = new Quill('#status-editor', {
                modules: {
                    toolbar: {
                        container: [
                            [
                                {'font': []},
                                {'size': []}
                            ],
                            [
                                'bold',
                                'italic',
                                'underline',
                                'strike'
                            ],
                            [
                                {'color': []},
                                {'background': []}
                            ],
                            [
                                {'header': '1'},
                                {'header': '2' },
                                'blockquote',
                                'code-block'
                            ],
                            [
                                {'list': 'ordered'},
                                {'list': 'bullet'},
                                {'indent': '-1'},
                                {'indent': '+1'}
                            ],
                            [
                                'direction',
                                {'align': []}
                            ],
                            [
                                'link',
                                'image',
                                'video'
                            ],
                            [
                                'clean'
                            ]
                        ],
                    }
                },
                theme: 'snow'
            });
        }

        if (window.audio_embeds) {
            $.extend(audio_embeds, window.audio_embeds);
        }
        if (window.video_embeds) {
            $.extend(video_embeds, window.video_embeds);
        }

        $(document).on('keypress', 'span.link', function(e) {
            if (e.keyCode === 13) {
                $(this).click();
            }
        });

        /* You may overwrite it in your user-scripts.js */
        social_sharing_sites = window.social_sharing_sites || [{
            name: 'E-mail',
            href: 'mailto:?subject={URL}&body={TITLE}',
            className: 'email'
        }, {
            name: 'Twitter',
            href: 'https://twitter.com/?status={TITLE}:%20{URL}',
            className: 'twitter'
        }, {
            name: 'Facebook',
            href: 'https://www.facebook.com/sharer.php?u={URL}&t={TITLE}',
            className: 'facebook'
        }, {
            name: 'Reddit',
            href: 'https://reddit.com/submit?url={URL}&title={TITLE}',
            className: 'reddit'
        }];

        const $scrollToTopButton = $(".scroll-to-top");

        $(window).scroll(function() {
            if ($(this).scrollTop() > 100) {
                $scrollToTopButton.fadeIn();
            }
            else {
                $scrollToTopButton.fadeOut();
            }
        });

        $scrollToTopButton.click(function() {
            scroll_to_top();
            return false;
        });

        const parsedUrl = new URL(window.location);
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
            if (quill) {
                quill.clipboard.dangerouslyPasteHTML(body);
            }
            else {
                $('#status').val(body.replace(/<br>/g, '\n'));
            }
        }
    });

    function init_settings() {
        $('#add-service a').click(function() {
            show_spinner(this);
            get_service_form({
                method: 'get',
                api: this.className
            }, '#add-service');
            return false;
        });
        $(document).on('click', '#edit-service a', function() {
            if (this.id && this.id.indexOf('service-') === 0) {
                show_spinner(this);
                get_service_form({
                    method: 'get',
                    id: parse_id(this.id)[1]
                }, this);
                return false;
            }
        });
        $('#select-list').change(function() {
            if (this.value !== '') {
                window.location = baseurl + 'settings/lists/' + this.value;
            }
            else {
                window.location = baseurl + 'settings/lists';
            }
        });
        $('#settings input[name=cancel]').click(hide_settings_form);
        $('#list-form a').click(function() {
            if (!confirm(_('Are you sure?'))) {
                return false;
            }
            const form = $('#list-form');
            form.append(DCE('input', {
                type: 'hidden',
                name: 'delete',
                value: 1
            }));
            form.submit();
            return false;
        });
        $('#websub-subs a').click(function() {
            if (!confirm(_('Are you sure?'))) {
                return false;
            }
            show_spinner(this);
            const id = parse_id(this.id)[1];
            const form = $('#websub-form');
            $('select').attr('disabled', 'disabled');
            form.append(DCE('input', {
                type: 'hidden',
                name: 'unsubscribe',
                value: id
            }));
            form.submit();
            return false;
        });
        $('#change-theme').click(change_theme);
    }

    function get_service_form(params, dest) {
        $.ajax({
            url: baseurl + 'settings/api/service',
            data: $.param(params),
            dataType: 'json',
            type: 'POST',
            success: function(json) {
                hide_spinner();
                const f = prepare_service_form(json);
                $(dest).after(f);
                $(f).fadeIn('normal', function() {
                    scroll_to_element(f, 120);
                    $('input[type=text]:first', f).focus();
                });
            }
        });
    }

    function hide_settings_form() {
        $('#service-form').fadeOut();
    }

    function submit_service_form() {
        let dest = $(this).next();
        if (dest.length === 0) {
            dest = $(this).parent();
        }
        show_spinner($('input[type=submit]', this));

        const form = $('#service-form');
        const params = form.serializeArray();
        params.push({
            name: 'method',
            value: 'post'
        });

        $.ajax({
            url: form.attr('action'),
            data: $.param(params),
            dataType: 'json',
            type: 'POST',
            success: function(json) {
                hide_spinner();
                const f = prepare_service_form(json);
                dest.append(f);
                $(f).show();
            }
        });
        return false;
    }

    let settings_deps = null;
    const settings_onchange_field = function() {
        if (this.id in settings_deps) {
            let deps = settings_deps[this.id];
            for (let i = 0; i < deps.length; i++) {
                let val = deps[i][0];
                let row = deps[i][1];
                if (this.value === val) {
                    $('input', row).removeAttr('disabled');
                    row.style.display = 'block';
                }
                else {
                    $('input', row).attr('disabled', 'disabled');
                    row.style.display = 'none';
                }
            }
        }
    };

    function prepare_service_form(data) {
        let form = document.getElementById('service-form');
        if (!form) {
            form = DCE('form', {
                id: 'service-form',
                style: {
                    display: 'none'
                }
            }, [DCE('fieldset', {
                className: 'aligned'
            })]);
        }
        $(form).hide();

        const fs = $('fieldset:first', form);
        fs.empty();
        settings_deps = {};

        if (data) {
            form.action = data.action;
            form.onsubmit = submit_service_form;

            if (data.id) {
                fs.append(DCE('input', {
                    type: 'hidden',
                    name: 'id',
                    value: data.id
                }));
            }
            fs.append(DCE('input', {
                type: 'hidden',
                name: 'api',
                value: data.api
            }));

            let obj;

            for (let i = 0; i < data.fields.length; i++) {
                const f = data.fields[i];

                if (f.type === 'select') {
                    obj = DCE('select', {
                        id: f.name,
                        name: f.name,
                        value: f.value
                    });
                    for (let j = 0; j < f.options.length; j++) {
                        const opt = f.options[j];
                        const sel = opt[0] === f.value ? true : false;
                        obj.options[obj.options.length] = new Option(
                            opt[1], opt[0], sel, sel);
                    }
                }
                else if (f.type === 'checkbox') {
                    obj = DCE('input', {
                        type: f.type,
                        id: f.name,
                        name: f.name,
                        value: '1',
                        checked: f.checked
                    });
                }
                else if (f.type === 'link') {
                    obj = DCE('a', {
                        id: f.name,
                        href: f.href
                    }, [f.value]);
                    if (f.name === 'oauth_conf') {
                        obj.onclick = function() {
                            oauth_configure(data.id);
                            return false;
                        };
                    }
                    else if (f.name === 'oauth2_conf') {
                        obj.onclick = function() {
                            oauth2_configure(data.id);
                            return false;
                        };
                    }
                }
                else {
                    obj = DCE('input', {
                        type: f.type,
                        id: f.name,
                        name: f.name,
                        value: f.value,
                        size: 32,
                        maxlength: 80,
                        autocomplete: 'off'
                    });
                }

                let hint = false;
                if (f.hint) {
                    hint = DCE('span', {
                        className: 'hint'
                    }, [f.hint]);
                }

                const miss = f.miss ? 'missing' : '';
                const row = DCE('div', {
                    className: 'form-row'
                }, [DCE('label', {
                    htmlFor: f.name,
                    className: miss
                }, [f.label]), hint, obj, false]);
                if (f.deps) {
                    for (let name in f.deps) {
                        if (!settings_deps[name]) {
                            settings_deps[name] = [];
                        }
                        settings_deps[name].push([f.deps[name], row]);
                    }
                }
                fs.append(row);
            }
            for (let name in settings_deps) {
                $('#' + name).change(settings_onchange_field).change();
            }

            const row = DCE('div', {
                className: 'form-row'
            });
            if (data.save) {
                row.appendChild(DCE('input', {
                    type: 'submit',
                    id: 'save',
                    value: data.save
                }));
            }
            row.appendChild(DCE('input', {
                type: 'button',
                id: 'cancel',
                value: data.cancel,
                onclick: hide_settings_form
            }));
            if (data['delete']) {
                row.appendChild(document.createTextNode(' '));
                row.appendChild(DCE('a', {
                    href: baseurl + 'admin/stream/service/' +
                        data.id + '/delete/',
                    target: 'admin',
                    onclick: hide_settings_form
                }, [data['delete']]));
            }
            fs.append(row);

            if (data['need_import']) {
                $('#edit-service').prepend(
                    '<li><span class="service ' + data.api +
                        '"></span><a class="' + data.api +
                        '" id="service-' + data.id +
                        '" href="#">' + data.name + '</a></li>');
                $.post(baseurl + 'settings/api/import', {
                    id: data.id
                });
            }
        }
        return form;
    }

    function oauth_configure(id) {
        const p = MDOM.get_win_center(800, 480);
        window.open('oauth/' + id, 'oauth', 'width=' + p.width + ',height=' + p.height + ',left=' + p.left + ',top=' + p.top + ',toolbar=no,status=yes,location=no,resizable=yes' + ',scrollbars=yes');
    }

    function oauth2_configure(id) {
        const p = MDOM.get_win_center(800, 480);
        window.open('oauth2/' + id, 'oauth2', 'width=' + p.width + ',height=' + p.height + ',left=' + p.left + ',top=' + p.top + ',toolbar=no,status=yes,location=no,resizable=yes' + ',scrollbars=yes');
    }

    const MDOM = {
        'center': function(obj, objWidth, objHeight) {
            let innerWidth = 0;
            let innerHeight = 0;
            if (!objWidth && !objHeight) {
                objWidth = $(obj).width();
                objHeight = $(obj).height();
                if (objWidth === '0px' || objWidth === 'auto') {
                    objWidth = obj.offsetWidth + 'px';
                    objHeight = obj.offsetHeight + 'px';
                }
                if (objHeight.indexOf('px') === -1) {
                    obj.style.display = 'block';
                    objHeight = obj.clientHeight;
                }
                objWidth = parseInt(objWidth);
                objHeight = parseInt(objHeight);
            }
            if (window.innerWidth) {
                innerWidth = window.innerWidth / 2;
                innerHeight = window.innerHeight / 2;
            }
            else if (document.body.clientWidth) {
                innerWidth = $(window).width() / 2;
                innerHeight = $(window).height() / 2;
            }
            let wleft = innerWidth - (objWidth / 2);
            if (wleft < 0) {
                wleft = 0;
            }
            obj.style.left = wleft + 'px';
            obj.style.top = $(document).scrollTop() + innerHeight -
                (objHeight / 2) + 'px';
            if (parseInt(obj.style.top) < 1) {
                obj.style.top = '1px';
            }
        },
        'get_win_center': function(width, height) {
            const screenX = typeof window.screenX !== 'undefined' ?
                window.screenX : window.screenLeft;
            const screenY = typeof window.screenY !== 'undefined' ?
                window.screenY : window.screenTop;
            const outerWidth = typeof window.outerWidth !== 'undefined' ?
                window.outerWidth : document.body.clientWidth;
            const outerHeight = typeof window.outerHeight !== 'undefined' ?
                window.outerHeight : (document.body.clientHeight - 22);
            return {
                width: width,
                height: height,
                left: parseInt(screenX + ((outerWidth - width) / 2), 10),
                top: parseInt(screenY + ((outerHeight - height) / 2.5), 10)
            };
        }
    };

    const Shareitbox = new function() {
        const self = this;
        let initied = false;
        let sbox = null;

        this.init = function() {
            if (initied) {
                return;
            }
            sbox = document.createElement('div');
            sbox.id = 'shareitbox';
            sbox.style.display = 'none';
            document.body.appendChild(sbox);
            initied = true;
        };

        this.open = function(opts) {
            self.init();
            let width = opts.width || 270;
            let height = opts.height || 130;
            let url = opts.url || '';
            let title = opts.title || '';
            let reshareit = opts.reshareit || false;

            Overlay.enable(40);
            const o = DCE('div');
            for (let i in social_sharing_sites) {
                let s = social_sharing_sites[i];
                let href = s.href.replace('{URL}', encodeURIComponent(url));
                href = href.replace('{TITLE}', encodeURIComponent(title));

                let img;
                if (s.className) {
                    img = DCE('span', {
                        className: 'share-' + s.className
                    });
                }
                else if (s.icon) {
                    img = DCE('img', {
                        src: s.icon,
                        width: 16,
                        height: 16
                    });
                }

                o.appendChild(DCE('div', {
                    className: 'item'
                }, [DCE('a', {
                    href: href,
                    target: '_blank'
                }, [img, document.createTextNode(String.fromCharCode(160)),
                    document.createTextNode(s.name)
                   ])]));
            }

            // Web Share API
            if (navigator.share) {
                let img = DCE('span', {
                    className: 'share-webshare'
                });
                o.appendChild(DCE('div', {
                    className: 'item'
                }, [DCE('a', {
                    href: '#',
                    onclick: function() {
                        try {
                            navigator.share({
                                title: title,
                                url: url,
                            });
                        }
                        catch (e) {
                        }
                    }
                }, [img, document.createTextNode(String.fromCharCode(160)),
                    document.createTextNode('Web Share')
                ])]));
            }

            if (reshareit) {
                sbox.appendChild(DCE('div', {
                    className: 'reshare'
                }, [DCE('a', {
                    id: 'reshare-' + opts.id,
                    href: '#',
                    onclick: reshare_entry
                }, [_('Reshare it at your stream')]),
                    document.createTextNode(' ' + _('or elsewhere:') + ' ')
                   ]));
            }
            else {
                sbox.appendChild(DCE('div', {
                    className: 'reshare'
                }, [_('Share or bookmark this entry')]));
            }
            sbox.appendChild(o);

            if (typeof width == 'number') {
                sbox.style.width = width + 'px';
            }
            else {
                sbox.style.width = width;
            }
            if (typeof height == 'number') {
                sbox.style.height = height + 'px';
            }
            else {
                sbox.style.height = height;
            }
            sbox.style.position = 'absolute';
            MDOM.center(sbox, $(sbox).width(), $(sbox).height());
            sbox.style.display = 'block';

            $('#overlay').click(this.close);
            document.onkeydown = function(e) {
                let code;
                if (!e) {
                    e = window.event;
                }
                if (e.keyCode) {
                    code = e.keyCode;
                }
                else if (e.which) {
                    code = e.which;
                }
                if (code === 27) { /* escape */
                    self.close();
                    return false;
                }
                return true;
            };

            return false;
        };

        this.close = function() {
            document.onkeydown = null;
            sbox.style.display = 'none';
            sbox.innerHTML = '';
            Overlay.disable();
        };
    };

    const Graybox = new function() {
        const self = this;
        let initied = false;
        let gb = null;

        this.init = function() {
            if (initied) {
                return;
            }
            gb = document.createElement('div');
            gb.id = 'graybox';
            gb.style.display = 'none';
            document.body.appendChild(gb);
            initied = true;
        };

        this.scan = function(ctx) {
            self.init();
            const $imgs = $('.thumbnails > a:has(img)', ctx);
            $imgs.each(function(i, v) {
                this.rel = $(v).closest('article').get(0).id;
            });
            $imgs.click(self.open_img);
        };

        this.open_img = function() {
            let href = this.href;
            let type = undefined;

            if (href.match(/friendfeed-media\.com/)) {
                type = 'image';
            }
            else if (href.match(/twitpic\.com\/(\w+)/)) {
                href = 'http://twitpic.com/show/full/' + RegExp.$1;
                type = 'image';
            }
            else if (href.match(/twitter\.com\//)) {
                href = $(this).data('imgurl');
                type = 'image';
            }
            else if (href.match(/instagram\.com\/p\/([\w\-]+)\/?/)) {
                href = 'https://instagram.com/p/' + RegExp.$1 + '/media/?size=l';
                type = 'image';
            }
            else if (href.match(/instagr\.am\/p\/([\w\-]+)\/?/)) {
                href = 'https://instagram.com/p/' + RegExp.$1 + '/media/?size=l';
                type = 'image';
            }
            else if (href.match(/yfrog\.com\/(\w+)/)) {
                href = 'https://yfrog.com/' + RegExp.$1 + ':iphone';
                type = 'image';
            }
            else if (href.match(/bp\.blogspot\.com/))
                href = href.replace(/-h\//, '/');

            return self.open({
                src: href,
                type: type,
                obj: this
            });
        };

        this.open = function(opts) {
            let src = opts.src;
            let width = opts.width || 425;
            let height = opts.height || 344;
            let type = opts.type || undefined;
            let obj = opts.obj || undefined;

            if (!type) {
                if (src.match(/(\.jpg$|\.jpeg$|\.webp$|\.avif$|\.heif$|\.png$|\.gif$)/i)) {
                    type = 'image';
                }
                else {
                    return true;
                }
            }

            if ('fancybox' in $) {
                let imgs = [{src: src}];
                let index = 0;
                if (obj.rel && obj.rel !== '' && obj.rel !== 'nofollow') {
                    const $r = $('a[rel=' + obj.rel + ']');
                    if ($r.length > 1) {
                        imgs = [];
                        $r.each(function(i, v) {
                            imgs.push({src: v.href});
                            if (src === v.href) {
                                index = i;
                            }
                        });
                    }
                }
                $.fancybox.open(imgs, {
                    type: type,
                    index: index,
                    centerOnScroll: true,
                    overlayColor: 'black',
                    overlayOpacity: 0.8,
                    padding: 2,
                    margin: 15,
                    transitionIn: 'elastic',
                    transitionOut: 'fade',
                    speedOut: 200,
                    loop: true
                });
                return false;
            }

            Overlay.enable();
            gb.innerHTML = '<div class="loading">' + _('Loading...') + '</div>';
            if (typeof width == 'number') {
                gb.style.width = width + 'px';
            }
            else {
                gb.style.width = width;
            }
            if (typeof height == 'number') {
                gb.style.height = height + 'px';
            }
            else {
                gb.style.height = height;
            }
            gb.style.position = 'absolute';
            MDOM.center(gb, $(gb).width(), $(gb).height());
            gb.style.display = 'block';

            $('#overlay').click(this.close);
            document.onkeydown = function(e) {
                let code;
                if (!e) {
                    e = window.event;
                }
                if (e.keyCode) {
                    code = e.keyCode;
                }
                else if (e.which) {
                    code = e.which;
                }
                if (code === 27) { /* escape */
                    self.close();
                    return false;
                }
                return true;
            };

            if (type === 'image') {
                const img = new Image();
                img.src = src;
                img.onerror = this.close;
                if (img.complete) {
                    show_image.call(img);
                }
                else {
                    img.onload = show_image;
                }
            }
            return false;
        };

        this.close = function() {
            document.onkeydown = null;
            gb.style.display = 'none';
            gb.innerHTML = '';
            Overlay.disable();
        };

        function show_image() {
            if (gb.style.display !== 'block') {
                return;
            }
            const img = this;
            let nscale;
            let maxWidth = $(window).width() - 100;
            if (img.width > maxWidth) {
                nscale = maxWidth / img.width;
                img.width = maxWidth;
                img.height = img.height * nscale;
            }
            let maxHeight = $(window).height() - 50;
            if (img.height > maxHeight) {
                nscale = maxHeight / img.height;
                img.height = maxHeight;
                img.width = img.width * nscale;
            }
            MDOM.center(gb, img.width, img.height);
            $(gb).animate({
                width: img.width + 'px',
                height: img.height + 'px'
            }, 500, function() {
                gb.innerHTML = '';
                gb.appendChild(img);
            });
        }
    };

    const Overlay = new function() {
        let visible = false;
        let ovl = null;
        this.enable = function(level) {
            if (typeof level === 'undefined') {
                level = '80';
            }
            if (visible) {
                return;
            }
            ovl = document.createElement('div');
            if (ovl) {
                const dh = $(document).height();
                const wh = $(window).height();
                ovl.id = 'overlay';
                ovl.style.position = 'absolute';
                ovl.style.width = '100%';
                ovl.style.height = ((dh > wh) ? dh : wh) + 'px';
                ovl.style.top = 0;
                ovl.style.left = 0;
                ovl.style.backgroundColor = 'black';
                ovl.style.opacity = '0.' + level;
                ovl.style.filter = 'alpha(opacity=' + level + ')';
                ovl.style.zIndex = '1000';
                ovl.style.display = 'block';
                document.body.appendChild(ovl);
                visible = true;
            }
        };
        this.disable = function() {
            if (ovl) {
                document.body.removeChild(ovl);
                visible = false;
            }
        };
    };

    function follow_href() {
        window.location = this.href;
        return false;
    }

    function focus_search() {
        if (this.value === this.PLACEHOLDER) {
            $(this).val('').removeClass('blur');
        }
    }

    function blur_search() {
        if (this.value === '') {
            $(this).val(this.PLACEHOLDER).addClass('blur');
        }
    }

    function set_placeholder(inputs, defval) {
        const has = 'placeholder' in document.createElement('input');
        for (let i = 0; i < inputs.length; i++) {
            const input = inputs[i];
            input.PLACEHOLDER = defval || input.getAttribute('placeholder');
            if (!has) {
                input.autocomplete = 'off';
                input.onfocus = focus_search;
                input.onblur = blur_search;
                if (input.value === '' || input.value === input.PLACEHOLDER) {
                    $(input).val(input.PLACEHOLDER).addClass('blur');
                }
            }
        }
    }

    function pad(number, len) {
        let str = '' + number;
        while (str.length < len)
            str = '0' + str;
        return str;
    }

    function strip_tags_trim(s) {
        return s.replace(/<\/?[^>]+>/gi, '').replace(/^\s+|\s+$/g, '');
    }

    function DCE(name, props, content_list) {
        const obj = document.createElement(name);
        if (obj) {
            if (props) {
                for (let p in props) {
                    if (p === 'style') {
                        for (let s in props[p])
                            obj.style[s] = props.style[s];
                    }
                    else {
                        obj[p] = props[p];
                    }
                }
            }
            if (content_list) {
                for (let i = 0; i < content_list.length; i++) {
                    const content = content_list[i];
                    if (typeof content == 'string' ||
                        typeof content == 'number') {
                        obj.innerHTML = content;
                    }
                    else if (typeof content == 'object') {
                        obj.appendChild(content);
                    }
                }
            }
        }
        return obj;
    }

    let audio_embeds = {
    };
    let video_embeds = {
        'youtube': '<iframe width="560" height="349" src="https://www.youtube.com/embed/{ID}?autoplay=1&rel=0" frameborder="0" allowfullscreen></iframe>',
        'vimeo': '<iframe width="560" height="315" src="https://player.vimeo.com/video/{ID}?autoplay=1" frameborder="0" allowfullscreen></iframe>',
        'dailymotion': '<iframe width="560" height="315" src="https://www.dailymotion.com/embed/video/{ID}?autoplay=1" frameborder="0"></iframe>'
    };
})();
