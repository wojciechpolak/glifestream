/*
 *  gLifestream Copyright (C) 2009, 2010, 2011, 2013 Wojciech Polak
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
    var a = parse_id ($(this).data ('id') || this.id);
    var type = a[0];
    var id = a[1];

    if (type in video_embeds)
      var embed = video_embeds[type].replace (/{ID}/g, id);
    else
      return true;

    $('.playbutton', this).removeClass ('playbutton').addClass ('stopbutton');
    $VC (this).after ('<div class="player video ' +
		      type + '">' + embed + '</div>');
    $('a', this).blur ();
    scroll_to_element (this);
    return false;
  }

  function stop_video () {
    $('.player', $VC (this).parent ()).remove ();
    $('.stopbutton', this).removeClass ('stopbutton').addClass ('playbutton');
    $('a', this).blur ();
    return false;
  }

  function toggle_video () {
    var $this = $(this);
    if (!$this.hasClass ('video-inline')) {
      if ($('.playbutton', this).length)
	play_video.call (this);
      else
	stop_video.call (this);
    }
    else {
      if (!$this.data ('play')) {
	$this.data ('play', true);
	play_video.call (this);
      }
      else {
	stop_video.call (this);
	$this.data ('play', false);
      }
    }
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

  function play_audio (e) {
    if (e.which && e.which !== 1)
      return false;
    var a = parse_id ($(this).data ('id') || this.id);
    var type = a[0];
    $('a', this).blur ();

    if ($('.player', this.parentNode).length) {
      $('.player', this.parentNode).remove ();
      return false;
    }

    if (type == 'audio')
      var embed = '<audio src="'+ $('a', this).attr ('href') +'" controls="true" autoplay="autoplay">'+ _('Your browser does not support it.') +'</audio>';
    else if (type in audio_embeds)
      var embed = audio_embeds[type];
    else
      return true;

    if (type == 'thesixtyone') {
      var data = a[1].split ('-');
      var artist = data[0];
      var id = data[1];
      embed = embed.replace ('{ARTIST}', artist);
    }
    else if (type == 'mp3')
      var id = $('a', this).attr ('href');
    else
      var id = a[1];

    embed = embed.replace (/{ID}/g, id);

    $('.player').remove ();
    $(this.parentNode).append ('<div class="player audio">' + embed + '</div>');
    return false;
  }

  /* find menu */
  function $M (entry) {
    return $('.entry-controls-switch', entry.parentNode.parentNode.parentNode)[0];
  }

  function load_entries () {
    var that = this;
    if (that.busy) return false;
    that.busy = true;
    if (articles.length >= continuous_reading)
      return follow_href.call (this);
    show_spinner (this);
    var url = this.href;
    url += (url.indexOf ('?') != -1) ? '&' : '?';
    url += 'format=html-pure';
    $.getJSON (url, function (json) {
	hide_spinner ();
	that.busy = false;
	var num = articles.length;
	$(articles[num - 1]).after (json.stream);
	nav_next.each (function () {
	    var s = this.href.indexOf ('start=');
	    if (s != -1 && json.next)
	      this.href = this.href.substring (0, s + 6) + json.next;
	    else {
	      s = this.href.indexOf ('page=');
	      if (s != -1 && json.next)
		this.href = this.href.substring (0, s + 5) + json.next;
	      else
		$(this).remove ();
	    }
	  });
	articles = $('#stream article');
	num = articles.length - num;
	var latest = $('#stream article').slice (-num);
	Graybox.scan (latest);
	alter_html (latest);
	$('a.map', latest).each (render_map);
	scaledown_images ($('img', latest));
	scroll_to_element (latest[0], 25);
      });
    return false;
  }

  function hide_entry (e) {
    if (e) e.preventDefault ();
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

  function favorite_entry (e) {
    if (e) e.preventDefault ();
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
  }

  function reshare_entry () {
    if (!confirm (_('You are about to re-share this entry at your stream. Confirm?')))
      return false;
    var as_me = !confirm (_('Keep the original author?'));
    var id = this.id.split ('-')[1];
    show_spinner (this);
    $.post (baseurl + 'api/reshare', { entry: id, as_me: as_me ? 1 : 0 },
	    function (html) {
	hide_spinner ();
	Shareitbox.close ();
	jump_to_top ();
	$('#stream').prepend (html);
	$('#stream article:first a.map').each (render_map);
	scaledown_images ('#stream article:first img');
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

  function edit_entry (e) {
    if (e) e.preventDefault ();
    var that = this;
    var id = this.id.split ('-')[1];
    show_spinner ($M (this));
    $.post (baseurl + 'api/getcontent', {entry: id, raw: 1}, function (html) {
	hide_spinner ();
	var ec = $(that).closest ('article').find ('.entry-content');
	var editor = $('#entry-editor');
	$('#edited-content').val (html);
	ec.after (editor);
	editor.fadeIn ('normal', function () {
	    scroll_to_element (editor, 400);
	  });
    });
  }

  function editor_handler (e) {
    var op = this.getAttribute ('name');
    if (op == 'cancel')
      $('#entry-editor').fadeOut ();
    else if (op == 'save') {
      show_spinner (this);
      var article = $(this).closest ('article').get (0);
      var id = parse_id (article.id)[1];
      $.post (baseurl + 'api/putcontent',
	      { entry: id, content: $('#edited-content').val () },
	      function (html) {
		hide_spinner ();
		$('#entry-'+ id +' .entry-content').html (html);
	      });
    }
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
    jump_to_top ();
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

  function alter_html (ctx) {
    $('.thumbnails a', ctx)
      .each (function (i) {
	  var id = false;
	  try {
	    if (this.href.indexOf ('http://www.youtube.com/watch') === 0)
	      id = 'youtube-' + this.href.substr (31);
	    else if (this.href.indexOf ('http://vimeo.com/') === 0)
	      id = 'vimeo-' + this.href.substr (17);
	    else if (this.href.indexOf ('http://www.collegehumor.com/video:') === 0)
	      id = 'chtv-' + this.href.substr (34);
	    else if (this.href.indexOf ('http://www.facebook.com/video/video.php?v=') === 0)
	      id = 'facebook-' + this.href.substr (42);
	    if (id) {
	      $(this).wrap ('<table class="vc"><tr><td><div id="'+ id +'" class="play-video"></div></td></tr></table>');
	      $(this).after ('<div class="playbutton"></div>');
	    }
	  } catch (e) {}
	});
    if (typeof window.user_alter_html == 'function')
      window.user_alter_html (ctx);
  }

  var gsc_load = false;
  var gsc_done = false;

  function open_sharing () {
    $('#share .fieldset').slideDown ('normal', function () {
	$('#status').focus ();
	if (!gsc_done)
	  get_selfposts_classes ();
      });
    return false;
  }

  function show_selfposts_classes () {
    var sc = $('#status-class').get (0);
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

  function open_more_sharing_options () {
    $(this).hide ();
    $('#more-sharing-options').fadeIn ();
    return false;
  }

  function share () {
    $(this).attr ('disabled', 'disabled');
    var docs = $('input[name=docs]');
    if (docs.length && docs.get (0).files && docs.get (0).files.length)
      return true;
    if (window.tinyMCE)
      var content = tinyMCE.get ('status').getContent ();
    else
      var content = $('#status').val ();
    if ($.trim (content) != '') {
      show_spinner (this);
      $.post (baseurl + 'api/share', { sid: $('#status-class').val (),
	    content: content,
	    draft: $('#draft').attr ('checked') ? 1 : 0,
	    friends_only: $('#friends-only').attr ('checked') ? 1 : 0 },
	function (html) {
	  hide_spinner ();
	  $('#stream').prepend (html);
	  $('#stream article:first a.map').each (render_map);
	  if (window.tinyMCE)
	    tinyMCE.get ('status').setContent ('');
	  else
	    $('#status').val ('');
	  $('#post').removeAttr ('disabled');
	  $('#share .fieldset').slideUp ();
	  scaledown_images ('#stream article:first img');
	});
    }
    else
      $('#post').removeAttr ('disabled');
    return false;
  }

  function get_map_embed (lat, lng) {
    if (settings.maps_engine == 'google') {
      return '<img src="https://maps.googleapis.com/maps/api/staticmap?sensor=false&zoom=12&size=175x120&markers='+ lat +','+ lng +'" alt="Map" width="175" height="120" />';
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
	  scaledown_images ($('img', article));
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
    if (y_diff > -20)
      s.css ('top', (pos.top - y_diff - 15) + 'px');

    return false;
  }

  function hide_menu_controls () {
    if (eco)
      $(eco).hide ().removeClass ('menu-expanded');
    document.onclick = null;
  }

  function scaledown_images (sel) {
    var maxwidth = $('#stream').width () - 80;
    $(sel || '#stream img').each (function (i) {
	if (this.complete) {
	  if (this.width > maxwidth) {
	    this.width = maxwidth;
	    if (this.style.width) {
	      var p = maxwidth * 100 / parseInt (this.style.width, 10);
	      this.style.width = maxwidth + 'px';
	      this.style.height = (this.height * p / 100) + 'px';
	    }
	  }
	}
	else {
	  this.onload = function () {
	    if (this.width > maxwidth) {
	      this.width = maxwidth;
	      if (this.style.width) {
		var p = maxwidth * 100 / parseInt (this.style.width, 10);
		this.style.width = maxwidth + 'px';
		this.style.height = (this.height * p / 100) + 'px';
	      }
	    }
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
	if ((current_article + 1) == articles.length)
	  nav_next.trigger ('click');
	else
	  highlight_article (articles[++current_article]);
	break;
      case 107: /* k */
	if ((current_article - 1) < 0) {
	  var prev = $('#stream a.prev');
	  if (prev.length)
	    window.location = prev.attr ('href');
	}
	else
	  highlight_article (articles[--current_article]);
	break;
      case 102: /* f */
	var ent = articles[current_article];
	if (ent) {
	  var c = $('span.favorite-control', ent);
	  if (c.length) favorite_entry.call (c[0]);
	}
	break;
      case 104: /* h */
	var ent = articles[current_article];
	if (ent) {
	  var id = ent.id.split ('-')[1];
	  var c = $('#hidden-' + id + ' a');
	  if (c.length)
	    unhide_entry.call (c[0]);
	  else {
	    var c = $('span.hide-control', ent);
	    if (c.length) hide_entry.call (c[0]);
	  }
	}
	break;
    }
  }

  function highlight_article (article) {
    $('a:first', article).focus ().blur ();
    articles.removeClass ('entry-highlight');
    $(article).addClass ('entry-highlight');
    scroll_to_element (article, 24);
  }

  function scroll_to_element (t, offset) {
    offset = offset || 16;
    var toffset = $(t).offset ().top - offset;
    $('html,body').animate ({scrollTop: toffset}, 200);
  }

  function jump_to_top () {
    if (document.body && document.body.scrollTop)
      document.body.scrollTop = 0;
    else if (document.documentElement && document.documentElement.scrollTop)
      document.documentElement.scrollTop = 0;
  }

  function gen_archive_calendar (year) {
    if (typeof stream_data == 'undefined')
      return;
    year = year || stream_data.view_date.split ('/')[0];
    var month = 1;
    var cal = '<table>';
    cal += '<tr><th colspan="3">'
      + '<a href="#" class="fleft prev">&nbsp;</a>';
    if (parseInt (year, 10) < stream_data.year_now)
      cal += '<a href="#" class="fright next">&nbsp;</a>';
    else
      cal += '<span class="fright" style="width:25px">&nbsp;</span>';
    cal += '<span class="year">'+ year +'</span> '
      + '</th></tr>';
    for (var row = 0; row < 4; row++) {
      cal += '<tr>';
      for (var col = 0; col < 3; col++, month++) {
	var d = year +'/'+ pad (month, 2);
	var u = d == stream_data.view_date ? ' class="view-month"' : '';
	if ($.inArray (d, stream_data.archives) != -1) {
	  var ctx = stream_data.ctx != '' ? stream_data.ctx + '/' : '';
	  cal += '<td> <a href="'+ settings.baseurl + ctx +
	    d +'/" rel="nofollow"'+ u +'>' +
	    stream_data.month_names[month - 1] +'</a></td>';
	}
	else
	  cal += '<td> '+ stream_data.month_names[month - 1] +'</td>';
      }
      cal += '</tr>';
    }
    cal += '</table>';
    $('#calendar').html (cal);
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
  var continuous_reading = 300;
  var social_sharing_sites = [];
  var nav_next = null;

  if (true) {
    var tags = 'article,aside,audio,footer,header,nav,section,time,video'.split (',');
    var i = tags.length;
    while (i--) { document.createElement (tags[i]); }
  }

  $(document).ready (function () {
      baseurl = settings.baseurl;

      if (document.getElementById ('settings')) {
	init_settings ();
	return;
      }

      Graybox.scan ();
      var stream = $('#stream').get (0);
      alter_html (stream);

      $('span.favorite-control', stream).live ('click', favorite_entry);
      $('span.hide-control', stream).live ('click', hide_entry);
      $('span.edit-control', stream).live ('click', edit_entry);
      $('a.shareit', stream).live ('click', shareit_entry);
      $('a.map', stream).each (render_map);
      $('a.show-map', stream).live ('click', show_map);
      $('a.expand-content', stream).live ('click', expand_content);
      $('span.entry-controls-switch', stream).live ('click', show_menu_controls);
      $('div.play-video,span.play-video', stream).live ('click', toggle_video);
      $('span.play-audio', stream).live ('click', play_audio);
      $('#change-theme').click (change_theme);
      $('div.lists select').change (function () {
	  if (this.value != '')
	    window.location = baseurl + 'list/' + this.value + '/';
	});
      $('#entry-editor input[type=button]').live ('click', editor_handler);

      gen_archive_calendar ();
      $('#calendar a.prev').live ('click', function () {
	  var year = parseInt ($('#calendar .year').html (), 10);
	  gen_archive_calendar (year - 1);
	  return false;
	});
      $('#calendar a.next').live ('click', function () {
	  var year = parseInt ($('#calendar .year').html (), 10);
	  gen_archive_calendar (year + 1);
	  return false;
	});

      scaledown_images ();

      articles = $('article', stream);
      nav_next = $('nav a.next', stream);
      document.onkeypress = kshortcuts;

      $('span.play-audio', stream).each (function () {
	  this.title = _('Click and Listen');
	});

      $('#status, #edited-content, form input[type=search]').
	focus (function () { document.onkeypress = null; }).
	blur (function () { document.onkeypress = kshortcuts; });

      $('form[name=searchform]').submit (function () {
	  var s = $('input[name=s]').get (0);
	  if (s && s.value != '' && s.value != s.PLACEHOLDER)
	    return true;
	  return false;
	});
      $('#search-submit').click (function () {
	  $('form[name=searchform]').submit ();
	});
      set_placeholder ($('input[placeholder]'));

      $('#ashare').click (open_sharing);
      $('#expand-sharing').click (open_more_sharing_options);
      $('#post').click (share);

      if (typeof window.continuous_reading != 'undefined')
	continuous_reading = parseInt (window.continuous_reading, 10);
      nav_next.click (continuous_reading ? load_entries : follow_href);

      if (window.tinyMCE) {
	tinyMCE.init ({
	  mode: 'exact',
	  elements: 'status',
	  width: '100%',
	  convert_urls: false,
	  entity_encoding: 'raw',
	  extended_valid_elements: 'div[*]',
	  plugins: 'insertdatetime,preview',
	  theme: 'advanced',
	  theme_advanced_toolbar_location: 'top',
	  theme_advanced_toolbar_align: 'left',
	  theme_advanced_statusbar_location: 'bottom',
	  theme_advanced_resizing: true,
	  theme_advanced_buttons1: 'bold,italic,underline,strikethrough,' +
	      '|,justifyleft,justifycenter,justifyright,justifyfull,' +
	      '|,formatselect,fontselect,fontsizeselect',
	  theme_advanced_buttons2: 'cut,copy,paste,pastetext,pasteword,' +
	      '|,search,replace,|,bullist,numlist,' +
	      '|,outdent,indent,blockquote,|,undo,redo,' +
	      '|,link,unlink,anchor,image,cleanup,code,' +
	      '|,insertdate,inserttime,preview,|,forecolor,backcolor',
	  theme_advanced_buttons3: ''
        });
      }

      if (window.audio_embeds)
	$.extend (audio_embeds, window.audio_embeds);
      if (window.video_embeds)
	$.extend (video_embeds, window.video_embeds);

      $('span.link').live ('keypress', function (e) {
	  if (e.keyCode == 13)
	    $(this).click ();
	});

      /* You may overwrite it in your user-scripts.js */
      social_sharing_sites = window.social_sharing_sites ||
	[{ name: 'E-mail', href: 'mailto:?subject={URL}&body={TITLE}', className: 'email'},
	 { name: 'Twitter', href: 'http://twitter.com/?status={TITLE}:%20{URL}', className: 'twitter'},
	 { name: 'Facebook', href: 'http://www.facebook.com/sharer.php?u={URL}&t={TITLE}', className: 'facebook'},
	 { name: 'FriendFeed', href: 'http://friendfeed.com/share?url={URL}&title={TITLE}', className: 'friendfeed'},
	 { name: 'Delicious', href: 'http://delicious.com/save?url={URL}&title={TITLE}', className: 'delicious'},
	 { name: 'Digg', href: 'http://digg.com/submit?phase=2&url={URL}&title={TITLE}', className: 'digg'},
	 { name: 'Reddit', href: 'http://reddit.com/submit?url={URL}&title={TITLE}', className: 'reddit'}];
    });

  function init_settings () {
    $('#add-service a').click (function () {
	show_spinner (this);
	get_service_form ({method: 'get', api:this.className}, '#add-service');
	return false;
      });
    $('#edit-service a').live ('click', function () {
	if (this.id && this.id.indexOf ('service-') == 0) {
	  show_spinner (this);
	  get_service_form ({method: 'get', id: parse_id (this.id)[1]}, this);
	  return false;
	}
      });
    $('#select-list').change (function () {
	if (this.value != '')
	  window.location = baseurl + 'settings/lists/' + this.value;
	else
	  window.location = baseurl + 'settings/lists';
      });
    $('#settings input[name=cancel]').click (hide_settings_form);
    $('#list-form a').click (function () {
	if (!confirm (_('Are you sure?')))
	  return false;
	var form = $('#list-form');
	form.append (DCE ('input', {type: 'hidden', name: 'delete', value: 1}));
	form.submit ();
	return false;
      });
    $('#pshb-subs a').click (function () {
	if (!confirm (_('Are you sure?')))
	  return false;
	show_spinner (this);
	var id = parse_id (this.id)[1];
	var form = $('#pshb-form');
	$('select').attr ('disabled', 'disabled');
	form.append (DCE ('input', {type: 'hidden', name: 'unsubscribe', value: id}));
	form.submit ();
	return false;
      });
    $('#openid_identifiers a').click (function () {
	if (!confirm (_('Are you sure?')))
	  return false;
	var id = parse_id (this.id)[1];
	var form = $('#oid-form');
	$('#oid-form input[name=openid_identifier]')
	  .attr ('disabled', 'disabled');
	form.append (DCE ('input', {type: 'hidden',
		name: 'delete', value: id}));
	form.submit ();
	return false;
      });
    $('#change-theme').click (change_theme);
  }

  function get_service_form (params, dest) {
    $.ajax ({ url: baseurl + 'settings/api/service',
	  data: $.param (params),
	  dataType: 'json',
	  type: 'POST',
	  success: function (json) {
	    hide_spinner ();
	    var f = prepare_service_form (json);
	    $(dest).after (f);
	    $(f).fadeIn ('normal', function () {
		scroll_to_element (f, 120);
		$('input[type=text]:first', f).focus ();
	      });
	}});
  }

  function hide_settings_form () {
    $('#service-form').fadeOut ();
  }

  function submit_service_form () {
    var dest = $(this).next ();
    if (dest.length == 0)
      dest = $(this).parent ();
    show_spinner ($('input[type=submit]', this));

    var form = $('#service-form');
    var params = form.serializeArray ();
    params.push ({name: 'method', value: 'post'});

    $.ajax ({ url: form.attr ('action'),
	  data: $.param (params),
	  dataType: 'json',
	  type: 'POST',
	  success: function (json) {
	    hide_spinner ();
	    var f = prepare_service_form (json);
	    dest.append (f);
	    $(f).show ();
	}});
    return false;
  }

  var settings_deps = null;
  var settings_onchange_field = function () {
    if (this.id in settings_deps) {
      var deps = settings_deps[this.id];
      for (var i = 0; i < deps.length; i++) {
	var val = deps[i][0];
	var row = deps[i][1];
	if (this.value == val) {
	  $('input', row).removeAttr ('disabled');
	  row.style.display = 'block';
	}
	else {
	  $('input', row).attr ('disabled', 'disabled');
	  row.style.display = 'none';
	}
      }
    }
  }

  function prepare_service_form (data) {
    var form = document.getElementById ('service-form');
    if (!form) {
      form = DCE ('form', {id: 'service-form', style: {display: 'none'}},
	       [DCE ('fieldset', {className: 'aligned'})]);
    }
    $(form).hide ();

    var fs = $('fieldset:first', form);
    fs.empty ();
    settings_deps = {};

    if (data) {
      form.action = data.action;
      form.onsubmit = submit_service_form;

      if (data.id)
	fs.append (DCE ('input', {type: 'hidden', name: 'id', value: data.id}));
      fs.append (DCE ('input', {type: 'hidden', name: 'api', value: data.api}));

      for (var i = 0; i < data.fields.length; i++) {
	var f = data.fields[i];

	if (f.type == 'select') {
	  var obj = DCE ('select', {id: f.name, name: f.name, value: f.value});
	  for (var j = 0; j < f.options.length; j++) {
	    var opt = f.options[j];
	    var sel = opt[0] == f.value ? true : false;
	    obj.options[obj.options.length] = new Option (opt[1], opt[0],
							  sel, sel);
	  }
	}
	else if (f.type == 'checkbox') {
	  var obj = DCE ('input', {type: f.type, id: f.name, name: f.name,
				   value: '1', checked: f.checked});
	}
	else if (f.type == 'link') {
	  var obj = DCE ('a', {id: f.name, href: f.href}, [f.value]);
	  if (f.name == 'oauth_conf')
	    obj.onclick = function () {
	      oauth_configure (data.id);
	      return false;
	    }
	}
	else {
	  var obj = DCE ('input', {type: f.type, id: f.name, name: f.name,
				   value: f.value, size: 32, maxlength: 80,
				   autocomplete: 'off'});
	}

	var hint = false;
	if (f.hint)
	  hint = DCE ('span', {className: 'hint'}, [f.hint]);

	var alink = false;
	if (data['need_fb_accesstoken'] && f.name == 'access_token') {
	  alink = DCE ('span', {},
		       [' ', DCE ('a', {href: '#', onclick: fb_get_access_token},
				  [data['need_fb_accesstoken']])]);
	}

	var miss = f.miss ? 'missing' : '';
	var row = DCE ('div', {className: 'form-row'},
		       [DCE ('label', {htmlFor: f.name, className: miss},
			     [f.label]), hint, obj, alink]);
	if (f.deps) {
	  for (var name in f.deps) {
	    if (!settings_deps[name])
	      settings_deps[name] = [];
	    settings_deps[name].push ([f.deps[name], row])
	  }
	}
	fs.append (row);
      }
      for (var name in settings_deps) {
	$('#' + name).change (settings_onchange_field).change ();
      }

      var row = DCE ('div', {className: 'form-row'});
      if (data.save) {
	row.appendChild (DCE ('input', {type: 'submit', id: 'save',
		value: data.save}));
      }
      row.appendChild (DCE ('input', {type: 'button', id: 'cancel',
	      value: data.cancel, onclick: hide_settings_form}));
      if (data['delete']) {
	row.appendChild (document.createTextNode (' '));
	row.appendChild (DCE ('a', {href: baseurl + 'admin/stream/service/'
		+ data.id + '/delete/', target: 'admin',
		onclick: hide_settings_form}, [data['delete']]));
      }
      fs.append (row);

      if (data['need_import']) {
	$('#edit-service').prepend ('<li><span class="service ' + data.api +
				    '"></span><a class="' + data.api +
				    '" id="service-' + data.id +
				    '" href="#">' + data.name + '</a></li>');
	$.post (baseurl + 'settings/api/import', {id: data.id});
      }
    }
    return form;
  }

  function fb_get_access_token () {
    FB.login (fb_handle_session, {perms: 'offline_access,read_stream'});
    return false;
  }

  function fb_handle_session (res) {
    if (!res.session || !res.perms)
      return;
    if (res.perms) {
      if (res.perms.indexOf ('read_stream') != -1 &&
	  res.perms.indexOf ('offline_access') != -1 &&
	  res.session['expires'] == 0) {
	$('#settings input[name=access_token]')
	  .val (res.session['access_token']);
      }
    }
  }

  function oauth_configure (id) {
    var p = MDOM.get_win_center (800, 480);
    window.open ('oauth/' + id, 'oauth', 'width=' + p.width
		 + ',height=' + p.height + ',left=' + p.left + ',top=' + p.top
		 + ',toolbar=no,status=yes,location=no,resizable=yes'
		 + ',scrollbars=yes');
  }

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
    },
    'get_win_center': function (width, height) {
      var screenX = typeof window.screenX != 'undefined' ?
                    window.screenX : window.screenLeft;
      var screenY = typeof window.screenY != 'undefined' ?
                    window.screenY : window.screenTop;
      var outerWidth = typeof window.outerWidth != 'undefined' ?
                       window.outerWidth : document.body.clientWidth;
      var outerHeight = typeof window.outerHeight != 'undefined' ?
                        window.outerHeight : (document.body.clientHeight - 22);
      return {
        width: width,
	height: height,
	left: parseInt (screenX + ((outerWidth - width) / 2), 10),
	top: parseInt (screenY + ((outerHeight - height) / 2.5), 10)
      };
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

	if (s.className)
	  var img = DCE ('span', {className: 'share-' + s.className});
	else if (s.icon)
	  var img = DCE ('img', {src: s.icon, width:16, height:16});

	o.appendChild
	  (DCE ('div', {className: 'item'},
		[DCE ('a', {href: href, target: '_blank'},
		      [img, document.createTextNode (String.fromCharCode (160)),
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

    this.scan = function (ctx) {
      self.init ();
      $imgs = $('.thumbnails > a:has(img)', ctx);
      $imgs.each (function (i, v) {
	  this.rel = $(v).closest ('article').get (0).id;
      });
      $imgs.click (self.open_img);
    };

    this.open_img = function () {
      var href = this.href;
      var type = undefined;

      if (href.match (/friendfeed-media\.com/)) {
	type = 'image';
      }
      else if (href.match (/twitpic\.com\/(\w+)/)) {
	href = 'http://twitpic.com/show/full/' + RegExp.$1;
	type = 'image';
      }
      else if (href.match (/twitter\.com\//)) {
	href = $(this).data ('imgurl');
	type = 'image';
      }
      else if (href.match (/lockerz\.com\/s\/(\d+)/) ||
	       href.match (/plixi\.com\/p\/(\d+)/) ||
	       href.match (/tweetphoto\.com\/(\d+)/)) {
	href = 'http://api.plixi.com/api/tpapi.svc/imagefromurl?size=big&url=http://lockerz.com/s/' + RegExp.$1;
	type = 'image';
      }
      else if (href.match (/instagram\.com\/p\/([\w\-]+)\/?/)) {
	href = 'http://instagram.com/p/'+ RegExp.$1 +'/media/?size=l';
	type = 'image';
      }
      else if (href.match (/instagr\.am\/p\/([\w\-]+)\/?/)) {
	href = 'http://instagr.am/p/'+ RegExp.$1 +'/media/?size=l';
	type = 'image';
      }
      else if (href.match (/yfrog\.com\/(\w+)/)) {
	href = 'http://yfrog.com/'+ RegExp.$1 +':iphone';
	type = 'image';
      }
      else if (href.match (/brizzly\.com\/pic\/(\w+)/)) {
	href = 'http://pics.brizzly.com/thumb_lg_'+ RegExp.$1 +'.jpg';
      }
      else if (href.match (/bp\.blogspot\.com/))
	href = href.replace (/-h\//, '/');

      return self.open ({src: href, type: type, obj: this});
    }

    this.open = function (opts) {
      var src    = opts.src;
      var width  = opts.width || 425;
      var height = opts.height || 344;
      var type   = opts.type || undefined;
      var obj    = opts.obj || undefined;

      if (!type) {
	if (src.match (/(\.jpg$|\.jpeg$|\.png$|\.gif$)/i))
	  type = 'image';
	else
	  return true;
      }

      if ('fancybox' in $) {
	var imgs = [src];
	var index = 0;
	if (obj.rel && obj.rel != '' && obj.rel != 'nofollow') {
	  var $r = $('a[rel='+ obj.rel +']');
	  if ($r.length > 1) {
	    imgs = [];
	    $r.each (function (i, v) {
		imgs.push (v.href);
		if (src == v.href)
		  index = i;
	      });
	  }
	}
	$.fancybox (imgs, {
	  type: type,
	  index: index,
	  centerOnScroll: true,
	  overlayColor: 'black',
	  overlayOpacity: 0.8,
	  padding: 2,
	  margin: 15,
	  transitionIn: 'elastic',
	  transitionOut: 'fade',
	  speedOut: 200
	});
	return false;
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

  function follow_href () {
    window.location = this.href;
    return false;
  }

  function focus_search () {
    if (this.value == this.PLACEHOLDER)
      $(this).val ('').removeClass ('blur');
  }

  function blur_search () {
    if (this.value == '')
      $(this).val (this.PLACEHOLDER).addClass ('blur');
  }

  function set_placeholder (inputs, defval) {
    var has = 'placeholder' in document.createElement ('input');
    for (var i = 0; i < inputs.length; i++) {
      var input = inputs[i];
      input.PLACEHOLDER = defval || input.getAttribute ('placeholder');
      if (!has) {
	input.autocomplete = 'off';
	input.onfocus = focus_search;
	input.onblur  = blur_search;
	if (input.value == '' || input.value == input.PLACEHOLDER)
	  $(input).val (input.PLACEHOLDER).addClass ('blur');
      }
    }
  }

  function pad (number, len) {
    var str = '' + number;
    while (str.length < len)
      str = '0' + str;
    return str;
  }

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

  var audio_embeds = {
    'thesixtyone': '<object type="application/x-shockwave-flash" width="310" height="120" data="http://www.thesixtyone.com/site_media/swf/song_player_embed.swf?song_id={ID}&artist_username={ARTIST}&autoplay=1"><param name="movie" value="http://www.thesixtyone.com/site_media/swf/song_player_embed.swf?song_id={ID}&artist_username={ARTIST}&autoplay=1"/></object>'
  };
  var video_embeds = {
    'youtube': '<iframe width="560" height="349" src="//www.youtube.com/embed/{ID}?autoplay=1&rel=0" frameborder="0" allowfullscreen></iframe>',
    'vimeo': '<iframe width="560" height="315" src="//player.vimeo.com/video/{ID}?autoplay=1" frameborder="0" allowfullscreen></iframe>',
    'chtv': '<iframe width="560" height="315" src="http://www.collegehumor.com/e/{ID}?autoplay=1" frameborder="0" allowfullscreen></iframe>',
    'ustream': '<iframe width="560" height="341" src="http://www.ustream.tv/embed/recorded/{ID}" scrolling="no" frameborder="0"></iframe>',
    'dailymotion': '<iframe width="560" height="315" src="http://www.dailymotion.com/embed/video/{ID}?autoplay=1" frameborder="0"></iframe>',
    'metacafe': '<object type="application/x-shockwave-flash" width="400" height="348" data="http://www.metacafe.com/fplayer/{ID}/video.swf"><param name="movie" value="http://www.metacafe.com/fplayer/{ID}/video.swf"/><param name="name" value="Metacafe_{ID}"/><param name="flashvars" value="playerVars=showStats=no|autoPlay=yes"/><param name="allowFullScreen" value="true"/><param name="allowScriptAccess" value="always"/></object>',
    'twitvid': '<iframe width="480" height="360" src="http://www.twitvid.com/embed.php?guid={ID}&autoplay=1" frameborder="0"></iframe>',
    'facebook': '<object type="application/x-shockwave-flash" width="560" height="315" data="http://www.facebook.com/v/{ID}"><param name="movie" value="http://www.facebook.com/v/{ID}"/><param name="allowFullScreen" value="true"/><param name="allowScriptAccess" value="always"/></object>',
    'googlevideo': '<object type="application/x-shockwave-flash" width="400" height="326" data="http://video.google.com/googleplayer.swf?docid={ID}&fs=true"><param name="movie" value="http://video.google.com/googleplayer.swf?docid={ID}&fs=true"/><param name="allowFullScreen" value="true"/><param name="allowScriptAccess" value="always"/></object>'
  };
})();
