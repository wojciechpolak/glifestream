/*
 *  gLifestream Copyright (C) 2009 Wojciech Polak
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
 *  with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

(function () {
  function parse_id (id) {
    var p = id.indexOf ('-');
    if (p == -1)
      return [id];
    return [id.substring (0, p), id.substr (p + 1)];
  }

  function play_video () {
    var a = parse_id (this.id);
    var type = a[0];
    var id = a[1];

    if (type == 'youtube') {
      var embed = '<object width="480" height="295"><param name="movie" value="http://www.youtube.com/v/'+ id +'&autoplay=1&showsearch=0&fs=1"></param><param name="allowFullScreen" value="true"><embed src="http://www.youtube.com/v/'+ id +'&autoplay=1&showsearch=0&fs=1" type="application/x-shockwave-flash" allowfullscreen="true" width="480" height="295"></embed></object>';
    }
    else if (type == 'vimeo') {
      var embed = '<object type="application/x-shockwave-flash" width="424" height="318" data="http://vimeo.com/moogaloop.swf?clip_id='+ id +'&server=vimeo.com&fullscreen=1&show_title=1&show_byline=1&show_portrait=1&color=&autoplay=1"><param name="quality" value="best"/><param name="allowfullscreen" value="true"/><param name="scale" value="showAll"/><param name="movie" value="http://vimeo.com/moogaloop.swf?clip_id='+ id +'&server=vimeo.com&fullscreen=1&show_title=1&show_byline=1&show_portrait=1&color=&autoplay=1"/></object>';
    }
    else if (type == 'chtv') {
      var embed = '<object type="application/x-shockwave-flash" width="480" height="270" data="http://www.collegehumor.com/moogaloop/moogaloop.swf?clip_id='+ id + '&fullscreen=1&autoplay=1"><param name="allowfullscreen" value="true"/><param name="wmode" value="transparent"/><param name="allowScriptAccess" value="always"/><param name="movie" quality="best" value="http://www.collegehumor.com/moogaloop/moogaloop.swf?clip_id='+ id + '&fullscreen=1&autoplay=1"/><embed src="http://www.collegehumor.com/moogaloop/moogaloop.swf?clip_id='+ id +'&fullscreen=1&autoplay=1" type="application/x-shockwave-flash" wmode="transparent" width="480" height="270" allowScriptAccess="always"></embed></object>';
    }
    else if (type == 'ustream') {
      var embed = '<embed flashvars="loc=%2F&autoplay=true&vid='+ id +'" width="480" height="386" allowfullscreen="true" allowscriptaccess="always" src="http://www.ustream.tv/flash/video/'+ id +'" type="application/x-shockwave-flash" />';
    }
    else if (type == 'dailymotion') {
      var embed = '<object width="480" height="381"><param name="movie" value="http://www.dailymotion.com/swf/'+ id +'?autoplay=1"></param><param name="allowFullScreen" value="true"></param><param name="allowScriptAccess" value="always"></param><embed src="http://www.dailymotion.com/swf/'+ id +'?autoplay=1" type="application/x-shockwave-flash" width="480" height="381" allowfullscreen="true" allowscriptaccess="always"></object>';
    }
    else if (type == 'metacafe') {
      var embed = '<embed flashvars="playerVars=showStats=no|autoPlay=yes" src="http://www.metacafe.com/fplayer/'+ id +'/video.swf" width="400" height="348" wmode="transparent" pluginspage="http://www.macromedia.com/go/getflashplayer" type="application/x-shockwave-flash" allowFullScreen="true" allowScriptAccess="always" name="Metacafe_'+ id +'"></embed>';
    }
    else if (type == 'twitvid') {
      var embed = '<object width="425" height="344"><param name="movie" value="http://www.twitvid.com/player/'+ id +'"></param><param name="allowFullScreen" value="true"></param><embed type="application/x-shockwave-flash" src="http://www.twitvid.com/player/'+ id +'" quality="high" allowscriptaccess="always" allowNetworking="all" allowfullscreen="true" wmode="transparent" width="425" height="344"></object>';
    }
    else if (type == 'vidly') {
      var embed = '<object width="480" height="269"><param name="movie" value="http://vid.ly/embed/'+ id +'"></param><param name="wmode" value="opaque"></param><param name="allowscriptaccess" value="always"></param><param name="allowfullscreen" value="true"></param><embed src="http://vid.ly/embed/'+ id +'" type="application/x-shockwave-flash" wmode="opaque" allowscriptaccess="always" allowfullscreen="true" width="480" height="269"></embed></object>';
    }
    else if (type == 'googlevideo') {
      var embed = '<embed id="VideoPlayback" src="http://video.google.com/googleplayer.swf?docid='+ id +'&fs=true" style="width:400px; height:326px" allowFullScreen="true" allowScriptAccess="always" type=application/x-shockwave-flash></embed>';
    }

    $('.playbutton', this).removeClass ('playbutton').addClass ('stopbutton');
    $VC (this).after ('<div class="player">' + embed + '</div>');
    $('a', this).blur ();
    scroll_to_element (this);
    return false;
  }

  function stop_video () {
    var a = parse_id (this.id);
    var type = a[0];
    var id = a[1];
    $('.player', $VC (this).parent ()).remove ();
    $('.stopbutton', this).removeClass ('stopbutton').addClass ('playbutton');
    $('a', this).blur ();
    return false;
  }

  /* find VC block */
  function $VC (obj) {
    if (obj.parentNode.tagName == 'TD') {
      obj = obj.parentNode.parentNode.parentNode.parentNode;
      if (obj.className == 'vc')
	return $(obj);
    }
    return $(obj);
  }

  function play_audio () {
    var a = parse_id (this.id);
    var type = a[0];
    $('a', this).blur ();

    if (type == 'audio') {
      var embed = '<audio src="'+ $('a', this).attr ('href') +'" controls="true">'+ _('Your browser does not support it.') +'</audio>';
    }
    else if (type == 'thesixtyone') {
      var data = a[1];
      var b = data.split ('-');
      var artist = b[0];
      var songid = b[1];
      var embed = '<object><embed src="http://www.thesixtyone.com/site_media/swf/song_player_embed.swf?song_id='+ songid +'&artist_username=' + artist + '&autoplay=1" type="application/x-shockwave-flash" wmode="transparent" width="310" height="120"></embed></object>';
    }
    else if (type == 'saynow') {
      var data = a[1];
      var embed = '<embed src="http://www.saynow.com/flash/sentplayer3.swf" quality="high" FlashVars="itemId='+ data +'&autoplay=0&duration=00:00&url=http://my.saynow.com" bgcolor="#ffffff" wmode="opaque" width="320" height="65" name="player" align="middle" allowScriptAccess="sameDomain" type="application/x-shockwave-flash" pluginspage="http://www.macromedia.com/go/getflashplayer"></embed>';
    }
    $('.player').remove ();
    $(this.parentNode).append ('<div class="player">' + embed + '</div>');
    scroll_to_element (this);
    return false;
  }

  /* find menu */
  function $M (entry) {
    return $('.entry-controls-switch', entry.parentNode.parentNode.parentNode)[0];
  }

  function hide_entry () {
    if (($('span.favorite', $M (this).parentNode).length)) {
      alert (_('Unfavorite this entry before hiding it.'));
      return false;
    }
    var id = this.id.split ('-')[1];
    show_spinner ($M (this));
    $.post (baseurl + 'api/hide', { entry: id }, function () {
	hide_spinner ();
	$('#entry-' + id).fadeOut ('normal', function () {
	    $(this).after ('<div id="hidden-'+ id +'" class="entry-hidden"><em>'+ _('Entry hidden') +'</em> - <a href="#" onclick="return gls.unhide_entry.call(this)">'+ _('Undo') +'</a></div>');
	  });
      });
    return false;
  }

  function unhide_entry () {
    var id = this.parentNode.id.split ('-')[1];
    show_spinner (this);
    $.post (baseurl + 'api/unhide', { entry: id }, function () {
	hide_spinner ();
	$('#hidden-' + id).remove ();
	$('#entry-' + id).fadeIn ();
      });
    return false;
  }

  function favorite_entry () {
    var that = this;
    var id = this.id.split ('-')[1];
    show_spinner ($M (this));
    if (!$(this).hasClass ('fav')) {
      $.post (baseurl + 'api/favorite', { entry: id }, function () {
	  hide_spinner ();
	  $($M (that)).before ('<span class="favorite"></span>');
	  $(that).addClass ('fav').html (_('Unfavorite'));
	});
    }
    else {
      $.post (baseurl + 'api/unfavorite', { entry: id }, function () {
	  hide_spinner ();
	  $('span.favorite', $M (that).parentNode).remove ();
	  $(that).removeClass ('fav').html (_('Favorite'));
	});
    }
    return false;
  }

  function reshare_entry () {
    if (!confirm (_('You are about to re-share this entry at your stream. Confirm?')))
      return false;
    var id = this.id.split ('-')[1];
    show_spinner (this);
    $.post (baseurl + 'api/reshare', { entry: id }, function (html) {
	hide_spinner ();
	$('#stream').prepend (html);
	$('#stream article:first .play-video').toggle (play_video, stop_video);
	$('#stream article:first a.map').each (render_map);
	scaledown_images ();
      });
    return false;
  }

  function shareit_entry () {
    var that = this.parentNode.parentNode;
    var id = this.id.split ('-')[1];
    var url = $('.entry-published a:eq(1)', that);
    if ($(that).hasClass ('private') && url.length)
      url = url.attr ('href');
    else {
      url = $('a[rel=bookmark]', that).attr ('href');
      if (window.location.href.indexOf (url) != -1)
	url = window.location.href;
      else
	url = 'http://' + window.location.host + url;
    }
    var title = $('.entry-title', that);
    if (title.length)
      title = strip_tags_trim (title.html ());
    else
      title = strip_tags_trim ($('.entry-content', that).html ());
    if (title.length > 137)
      title = title.substr (0, 137) + '...';
    Shareitbox.open ({ id: id, url: url, title: title,
	  reshareit: $(this).hasClass ('reshareit') });
    return false;
  }

  function translate_entry () {
    var that = this;
    var id = this.id.split ('-')[1];
    show_spinner ($M (this));
    $.post (baseurl + 'api/translate', { entry: id }, function (html) {
	hide_spinner ();
	var ctx = $('#entry-'+ id +' .entry-content');
	ctx.html (html);
	alter_thumbnails (ctx);
      });
    return false;
  }

  function change_theme () {
    var cookie_name = 'glifestream_theme';
    var cs = read_cookie (cookie_name);
    var idx = $.inArray (cs, settings.themes);

    if (!cs || idx == -1) {
      idx = 0;
      cs = settings.themes[idx];
    }
    if (idx < settings.themes.length - 1) idx++;
    else idx = 0;
    cs = settings.themes[idx];

    var date = new Date ();
    date.setTime (date.getTime () + (365 * 86400000));
    var expires = '; expires=' + date.toGMTString ();
    document.cookie = cookie_name +'='+ cs + expires + '; path=' + baseurl;
    if (document.body && document.body.scrollTop)
      document.body.scrollTop = 0;
    else if (document.documentElement && document.documentElement.scrollTop)
      document.documentElement.scrollTop = 0;
    window.location.reload ();
    return false;
  }

  function show_spinner (el) {
    if (el.blur) el.blur ();
    $(el).after ('<span id="spinner"></span>');
  }

  function hide_spinner () {
    $('#spinner').remove ();
  }

  function read_cookie (name) {
    var nameEq = name + '=';
    var ca = document.cookie.split (';');
    for (var i = 0; i < ca.length; i++) {
      var c = ca[i];
      while (c.charAt (0) == ' ')
	c = c.substring (1, c.length);
      if (c.indexOf (nameEq) == 0)
	return c.substring (nameEq.length, c.length);
    }
    return null;
  }

  function alter_thumbnails (ctx) {
    $('div.thumbnails a', ctx)
      .each (function (i) {
	  var id = false;
	  try {
	    if (this.href.indexOf ('http://www.youtube.com/watch') === 0)
	      id = this.href.substr (31);
	    else if (this.href.indexOf ('http://vimeo.com/') === 0)
	      id = 'vimeo-' + this.href.substr (17);
	    else if (this.href.indexOf ('http://www.collegehumor.com/video:') === 0)
	      id = 'chtv-' + this.href.substr (34);
	    if (id) {
	      $(this).wrap ('<table class="vc"><tr><td><div id="'+ id +'" class="play-video"></div></td></tr></table>');
	      $(this).after ('<div class="playbutton"></div>');
	    }
	  } catch (e) {}
	});
  }

  var gsc_load = false;
  var gsc_done = false;

  function open_sharing () {
    $('#share fieldset').slideDown ('normal', function () {
	$('#status').focus ();
	if (!gsc_done)
	  get_selfposts_classes ();
      });
    return false;
  }

  function show_selfposts_classes () {
    var sc = $('#status_class').get (0);
    for (var i in gsc_load) {
      sc.options[sc.options.length] = new Option (gsc_load[i]['cls'], gsc_load[i]['id']);
    }
    gsc_done = true;
  }

  function get_selfposts_classes () {
    if (!gsc_load) {
      $.getJSON (baseurl + 'api/gsc', function (json) {
	  gsc_load = json;
	  show_selfposts_classes ();
	});
    }
    else
      show_selfposts_classes ();
  }

  function share () {
    var status = $('#status');
    if ($.trim (status.val ()) != '') {
      show_spinner (this);
      $.post (baseurl + 'api/share', { id: $('#status_class').val (),
	    content: status.val () }, function (html) {
	  hide_spinner ();
	  $('#stream').prepend (html);
	  $('#stream article:first .play-video').toggle (play_video, stop_video);
	  $('#stream article:first a.map').each (render_map);
	  status.val ('');
	  $('#share fieldset').slideUp ();
	  scaledown_images ();
	});
    }
  }

  function get_map_embed (lat, lng) {
    if (settings.maps_engine == 'google') {
      return '<img src="http://maps.google.com/staticmap?zoom=12&size=175x120&maptype=mobile&markers='+ lat +','+ lng +'&key='+ settings.maps_key +'" alt="Map" width="175" height="120" />';
    }
    return '';
  }

  function render_map (i) {
    var lat = $('.latitude', this).html ();
    var lng = $('.longitude', this).html ();
    this.target = '_blank';
    this.parentNode.style.paddingLeft = 0;
    this.parentNode.style.background = 'none';
    $(this).html (get_map_embed (lat, lng));
  }

  function show_map () {
    this.blur ();
    if (this.folded)
      return true;
    var lat = $('.latitude', this).html ();
    var lng = $('.longitude', this).html ();
    this.target = '_blank';

    if (settings.maps_engine == 'google') {
      this.href = 'http://maps.google.com/?q=' + lat +','+ lng;
    }

    p = this.parentNode;
    $('a', p).html (get_map_embed (lat, lng));
    $(p).css ('paddingLeft', '0');
    this.folded = true;
    return false;
  }

  function expand_content () {
    var that = this;
    var article = this.parentNode.parentNode;
    if (article.content_loaded) {
      if (article.content_expanded) {
	$('div.entry-content', article).slideUp ();
	article.content_expanded = false;
      }
      else {
	$('div.entry-content', article).slideDown ();
	article.content_expanded = true;
      }
    }
    else {
      var id = parse_id (article.id)[1];
      show_spinner (this);
      $.post (baseurl + 'api/getcontent', { entry: id }, function (html) {
	  hide_spinner ();
	  $('div.entry-content', article).html (html).slideDown ();
	  article.content_loaded = true;
	  article.content_expanded = true;
	  scaledown_images ();
	});
    }
    return false;
  }

  var eco = null;
  function show_menu_controls () {
    hide_menu_controls ();
    var that = this;
    var s = $('.entry-controls', this.parentNode);
    var pos = $(this).position ();
    s.addClass ('menu-expanded')
      .css ({top: pos.top + 17, left: pos.left}).show ();
    eco = s[0];
    document.onclick = hide_menu_controls;

    var y_bottom = pos.top + s.height ();
    var y_diff = y_bottom - $(window).height () - $(document).scrollTop ();
    if (y_diff > 0)
      s.css ('top', (pos.top - y_diff - 15) + 'px');

    return false;
  }

  function hide_menu_controls () {
    if (eco)
      $(eco).hide ().removeClass ('menu-expanded');
    document.onclick = null;
  }

  function scaledown_images () {
    var maxwidth = $('#stream').width () - 100;
    $('#stream img').each (function (i) {
	if (this.complete) {
	  if (this.width > maxwidth)
	    this.width = maxwidth;
	}
	else {
	  this.onload = function () {
	    if (this.width > maxwidth)
	      this.width = maxwidth;
	    this.onload = null;
	  };
	}
      });
  }

  var articles = [];
  var current_article = -1;

  function kshortcuts (e) {
    var code;
    if (!e) var e = window.event;
    if (e.keyCode) code = e.keyCode;
    else if (e.which) code = e.which;
    if (e.ctrlKey || e.metaKey || e.altKey)
      return true;

    switch (code) {
      case 97: /* a */
	open_sharing ();
	break;
      case 106: /* j */
	if ((current_article + 1) == articles.length) {
	  var next = $('a.next');
	  if (next.length)
	    window.location = next.attr ('href');
	}
	else
	  highlight_article (articles[++current_article]);
	break;
      case 107: /* k */
	if ((current_article - 1) < 0) {
	  var prev = $('a.prev');
	  if (prev.length)
	    window.location = prev.attr ('href');
	}
	else
	  highlight_article (articles[--current_article]);
	break;
    }
  }

  function highlight_article (article) {
    $('a:first', article).focus ().blur ();
    articles.removeClass ('entry-highlight');
    $(article).addClass ('entry-highlight');
    scroll_to_element (article);
  }

  function scroll_to_element (t) {
    var toffset = $(t).offset ().top - 16;
    $('html,body').animate ({scrollTop: toffset}, 200);
  }

  function ajax_error (e) {
    alert (_('Communication Error. Try again.'));
    hide_spinner ();
  }

  function gettext (msg) {
    if (typeof gettext_msg != 'undefined' && gettext_msg[msg])
      return gettext_msg[msg];
    return msg;
  }

  function _(msg) {
    return gettext (msg);
  }

  function es (ns, p) {
    var t = ns.split (/\./);
    var a = window;
    for (var i = 0; i < t.length - 1; i++) {
      if (typeof a[t[i]] == 'undefined')
	a[t[i]] = {};
      a = a[t[i]];
    }
    a[t[t.length - 1]] = p;
  }

  es ('gls.unhide_entry', unhide_entry);
  $.ajaxSetup ({ error: ajax_error });
  var baseurl = '/';
  var social_sharing_sites = [];

  if (true) {
    var tags = 'article,aside,audio,footer,header,nav,section,time,video'.split (',');
    var i = tags.length;
    while (i--) { document.createElement (tags[i]); }
  }

  $(document).ready (function () {
      baseurl = settings.baseurl;
      Graybox.scan ();
      var stream = $('#stream').get (0);
      alter_thumbnails (stream);

      $('a.favorite-control', stream).live ('click', favorite_entry);
      $('a.hide-control', stream).live ('click', hide_entry);
      $('a.translate-control', stream).live ('click', translate_entry);
      $('a.shareit', stream).live ('click', shareit_entry);
      $('a.map', stream).each (render_map);
      $('a.show-map', stream).live ('click', show_map);
      $('a.expand-content', stream).live ('click', expand_content);
      $('a.entry-controls-switch', stream).live ('click', show_menu_controls);
      $('div.play-video,span.play-video', stream).toggle (play_video, stop_video);
      $('span.play-audio', stream).live ('click', play_audio);
      $('#change-theme').click (change_theme);
      $('#ashare').click (open_sharing);
      $('#post').click (share);
      $('div.lists select').change (function () {
	  if (this.value != '')
	    window.location = baseurl + 'list/' + this.value + '/';
	});
      $('div.archives select').change (function () {
	  if (this.value != '')
	    window.location = baseurl + this.value + '/';
	});
      scaledown_images ();

      articles = $('article', stream);
      document.onkeypress = kshortcuts;

      $('span.play-audio', stream).each (function () {
	  this.title = _('Click and Listen');
	});

      $('#status, form input[type=text]').
	focus (function () { document.onkeypress = null; }).
	blur (function () { document.onkeypress = kshortcuts; });

      $('form[name=searchform]').submit (function () {
	  return ($('input[name=s]').val () == '') ? false : true;
	});

      /* You may overwrite it in your user-scripts.js */
      social_sharing_sites = window.social_sharing_sites ||
	[{ name: 'E-mail', href: 'mailto:?subject={URL}&body={TITLE}', icon: baseurl + 'static/themes/default/icons/email.png'},
	 { name: 'Twitter', href: 'http://twitter.com/?status={TITLE}:%20{URL}', icon: 'http://twitter.com/favicon.ico'},
	 { name: 'FriendFeed', href: 'http://friendfeed.com/share?url={URL}&title={TITLE}', icon: 'http://friendfeed.com/favicon.ico'},
	 { name: 'Facebook', href: 'http://www.facebook.com/share.php?u={URL}&t={TITLE}', icon: 'http://www.facebook.com/favicon.ico'},
	 { name: 'Delicious', href: 'http://delicious.com/save?url={URL}&title={TITLE}', icon: 'http://delicious.com/favicon.ico'},
	 { name: 'Digg', href: 'http://digg.com/submit?phase=2&url={URL}&title={TITLE}', icon: 'http://digg.com/favicon.ico'},
	 { name: 'Reddit', href: 'http://reddit.com/submit?url={URL}&title={TITLE}', icon: 'http://www.reddit.com/favicon.ico'},
	 { name: 'Google', href: 'http://www.google.com/bookmarks/mark?op=add&bkmk={URL}&title={TITLE}', icon: 'http://www.google.com/favicon.ico'}];
    });

  var MDOM = {
    'center': function (obj, objWidth, objHeight) {
      var innerWidth = 0;
      var innerHeight = 0;
      if (!objWidth && !objHeight) {
	objWidth  = $(obj).width ();
	objHeight = $(obj).height ();
	if (objWidth == '0px' || objWidth == 'auto') {
	  objWidth = obj.offsetWidth + 'px';
	  objHeight = obj.offsetHeight + 'px';
	}
	if (objHeight.indexOf ('px') == -1) {
	  obj.style.display = 'block';
	  objHeight = obj.clientHeight;
	}
	objWidth = parseInt (objWidth);
	objHeight = parseInt (objHeight);
      }
      if (window.innerWidth) {
	innerWidth  = window.innerWidth / 2;
	innerHeight = window.innerHeight / 2;
      }
      else if (document.body.clientWidth) {
	innerWidth  = $(window).width () / 2;
	innerHeight = $(window).height () / 2;
      }
      var wleft = innerWidth - (objWidth / 2);
      if (wleft < 0) wleft = 0;
      obj.style.left = wleft + 'px';
      obj.style.top  = $(document).scrollTop () + innerHeight - (objHeight/2) + 'px';
      if (parseInt (obj.style.top) < 1)
	obj.style.top = '1px';
    }
  };

  var Shareitbox = new function () {
    var self = this;
    var initied = false;
    var sbox = null;

    this.init = function () {
      if (initied) return;
      sbox = document.createElement ('div');
      sbox.id = 'shareitbox';
      sbox.style.display = 'none';
      document.body.appendChild (sbox);
      initied = true;
    }

    this.open = function (opts) {
      self.init ();
      var width     = opts.width || 270;
      var height    = opts.height || 130;
      var url       = opts.url || '';
      var title     = opts.title || '';
      var reshareit = opts.reshareit || false;

      Overlay.enable (40);
      var o = DCE ('div');
      for (var i in social_sharing_sites) {
	var s = social_sharing_sites[i];
	var href = s.href.replace ('{URL}', encodeURIComponent (url));
	href = href.replace ('{TITLE}', encodeURIComponent (title));

	o.appendChild
	  (DCE ('div', {className: 'item'},
		[DCE ('a', {href: href, target: '_blank'},
		      [DCE ('img', {src: s.icon, width:16, height:16}),
		       document.createTextNode (String.fromCharCode (160)),
		       document.createTextNode (s.name)])]));
      }
      if (reshareit) {
	sbox.appendChild (DCE ('div', {className: 'reshare'},
			       [DCE ('a', {id: 'reshare-' + opts.id,
					   href: '#', onclick: reshare_entry},
				   [_('Reshare it at your stream')]),
				 document.createTextNode (' '+ _('or elsewhere:') +' ')]));
      }
      else {
	sbox.appendChild (DCE ('div', {className: 'reshare'},
			       [_('Share or bookmark this entry')]));
      }
      sbox.appendChild (o);

      if (typeof width == 'number')
	sbox.style.width = width + 'px';
      else
	sbox.style.width = width;
      if (typeof height == 'number')
	sbox.style.height = height + 'px';
      else
	sbox.style.height = height;
      sbox.style.position = 'absolute';
      MDOM.center (sbox, $(sbox).width (), $(sbox).height ());
      sbox.style.display = 'block';

      $('#overlay').click (this.close);
      document.onkeydown = function (e) {
	var code;
	if (!e) var e = window.event;
	if (e.keyCode) code = e.keyCode;
	else if (e.which) code = e.which;
	if (code == 27) { /* escape */
	  self.close ();
	  return false;
	}
	return true;
      };

      return false;
    };

    this.close = function () {
      document.onkeydown = null;
      sbox.style.display = 'none';
      sbox.innerHTML = '';
      Overlay.disable ();
    };
  };

  var Graybox = new function () {
    var self = this;
    var initied = false;
    var gb = null;

    this.init = function () {
      if (initied) return;
      gb = document.createElement ('div');
      gb.id = 'graybox';
      gb.style.display = 'none';
      document.body.appendChild (gb);
      initied = true;
    };

    this.scan = function () {
      self.init ();
      $('div.thumbnails a:has(img)').click (self.open_img);
    };

    this.open_img = function () {
      return self.open ({ src: this.href });
    }

    this.open = function (opts) {
      var src    = opts.src;
      var width  = opts.width || 425;
      var height = opts.height || 344;
      var type   = opts.type || undefined;

      if (!type) {
	if (src.match (/(\.jpg$|\.jpeg$|\.png$|\.gif$)/i) ||
	    src.match (/http:\/\/friendfeed-media.com/))
	  type = 'image';
	else
	  return true;
      }

      Overlay.enable ();
      gb.innerHTML = '<div class="loading">' + _('Loading...') + '</div>';
      if (typeof width == 'number')
	gb.style.width = width + 'px';
      else
	gb.style.width = width;
      if (typeof height == 'number')
	gb.style.height = height + 'px';
      else
	gb.style.height = height;
      gb.style.position = 'absolute';
      MDOM.center (gb, $(gb).width (), $(gb).height ());
      gb.style.display = 'block';

      $('#overlay').click (this.close);
      document.onkeydown = function (e) {
	var code;
	if (!e) var e = window.event;
	if (e.keyCode) code = e.keyCode;
	else if (e.which) code = e.which;
	if (code == 27) { /* escape */
	  self.close ();
	  return false;
	}
	return true;
      };

      if (type == 'image') {
	var img = new Image ();
	img.src = src;
	img.onerror = this.close;
	if (img.complete)
	  show_image.call (img);
	else
	  img.onload = show_image;
      }
      return false;
    };

    this.close = function () {
      document.onkeydown = null;
      gb.style.display = 'none';
      gb.innerHTML = '';
      Overlay.disable ();
    };

    function show_image () {
      if (gb.style.display != 'block')
	return;
      var img = this;
      var maxWidth = $(window).width () - 100;
      if (img.width > maxWidth) {
	var nscale = maxWidth / img.width;
	img.width  = maxWidth;
	img.height = img.height * nscale;
      }
      var maxHeight = $(window).height () - 50;
      if (img.height > maxHeight) {
	var nscale = maxHeight / img.height;
	img.height = maxHeight;
	img.width  = img.width * nscale;
      }
      MDOM.center (gb, img.width, img.height);
      $(gb).animate ({ width: img.width + 'px',
	    height: img.height + 'px'}, 500, function () {
	  gb.innerHTML = '';
	  gb.appendChild (img);
	});
    }
  };

  var Overlay = new function () {
    var visible = false;
    var ovl = null;
    this.enable = function (level) {
      if (typeof level == 'undefined')
	level = '80'
      if (visible) return;
      ovl = document.createElement ('div');
      if (ovl) {
	var dh = $(document).height ();
	var wh = $(window).height ();
	ovl.id = 'overlay';
	ovl.style.position = 'absolute';
	ovl.style.width  = '100%';
	ovl.style.height = ((dh > wh) ? dh : wh) + 'px';
	ovl.style.top  = 0;
	ovl.style.left = 0;
	ovl.style.backgroundColor = 'black';
	ovl.style.opacity = '0.' + level;
	ovl.style.filter  = 'alpha(opacity='+ level +')';
	ovl.style.zIndex  = '1000';
	ovl.style.display = 'block';
	document.body.appendChild (ovl);
	visible = true;
      }
    };
    this.disable = function () {
      if (ovl) {
	document.body.removeChild (ovl);
	visible = false;
      }
    };
  };

  function strip_tags_trim (s) {
    return s.replace (/<\/?[^>]+>/gi, '').replace (/^\s+|\s+$/g, '');
  }

  function DCE (name, props, content_list) {
    var obj = document.createElement (name);
    if (obj) {
      if (props) {
	for (var p in props) {
	  if (p == 'style') {
	    for (var s in props[p])
	      obj.style[s] = props.style[s]
	  }
	  else
	    obj[p] = props[p];
	}
      }
      if (content_list) {
	for (var i = 0; i < content_list.length; i++) {
	  var content = content_list[i];
	  if (typeof content == 'string' ||
	      typeof content == 'number')
	    obj.innerHTML = content;
	  else if (typeof content == 'object')
	    obj.appendChild (content);
	}
      }
    }
    return obj;
  }
})();
