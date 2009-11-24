{% load i18n %}
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
  var image_min_size = 30;
  var outline_size = 3;
  var shadow_size = 7;
  var available_images = [];

  function bookmarklet () {
    if (GID ('gls__container'))
      return;

    var selection;
    if (window.getSelection)
      selection = '' + window.getSelection ();
    else if (document.selection)
      selection = document.selection.createRange ().text;

    /* highlight all the images */
    var imgs = document.getElementsByTagName ('img');
    for (var i = 0; i < imgs.length; i++) {
      var img = imgs[i];
      if (img.width < image_min_size || img.height < image_min_size) {
	continue;
      }
      var listener = addEventListener (img, 'mouseover', curry (image_onmouseover, img));
      available_images.push ({
	element: img,
	cursor: img.style.cursor,
	listener: listener
      });
    }

    /* create the share dialog */
    var container = DCE
      ('div', {id: 'gls__container',
	       style: {position: 'absolute',
		       padding: 0, margin: 0, border: 0,
		       width: 'auto',
		       top: get_scroll_pos ().y + 'px', right: 0,
		       zIndex: 777777}},
	[DCE ('div', {id: 'gls__shadow',
		      style: {backgroundColor: 'black',
			      position: 'absolute',
			      padding: 0, margin: 0, border: 0,
			      top: 0, right: 0, zIndex: 0,
			      opacity: '0.30',
			      filter: 'alpha(opacity=30)'}}),
	 DCE ('div', {id: 'gls__foreground',
		      style: {backgroundColor: 'white',
			      position: 'relative',
			      padding: 0, margin: 0, border: 0,
			      width: '450px', height: '320px',
			      zIndex: 2}},
	   ['<iframe frameborder="0" id="gls__iframe" style="width:100%; height:100%; border:0; margin:0; padding:0;"></iframe>'])]
	);
    document.body.appendChild (container);

    var msg = {
      title: document.title,
      url: location.href
    };

    msg.selection = selection || '';
    var links = document.getElementsByTagName ('link');
    for (var i = 0; i < links.length; i++) {
      if (links[i].rel == 'image_src')
	msg.image = links[i].href;
      else if (links[i].rel == 'video_src')
	msg.video = links[i].href;
    }
    var metas = document.getElementsByTagName ('meta');
    for (var i = 0; i < metas.length; i++) {
      if (metas[i].name == 'video_thumb')
	msg.image = metas[i].content;
    }

    send_frame_message (msg);

    /* container for "click to include" images */
    var pc = DCE
      ('div', {id: 'gls__popup',
	       style: {position: 'absolute',
		       display: 'none',
		       padding: 0, margin: 0, border: 0,
		       top: 0, left: 0,
		       zIndex: 99999,
		       fontSize: '8pt',
		       fontFamily: 'Arial',
		       fontStyle: 'normal',
		       fontWeight: 'normal',
		       background: 'transparent'}});
    document.body.appendChild (pc);

    var last_shadow_width  = 0;
    var last_shadow_height = 0;

    function resize_shadow () {
      var shadow = GID ('gls__shadow');
      var foreground = GID ('gls__foreground');
      if (!shadow || !foreground) {
	clearInterval (interval);
	return;
      }
      if (last_shadow_width != foreground.offsetWidth ||
	  last_shadow_height != foreground.offsetHeight) {
	last_shadow_width  = foreground.offsetWidth;
	last_shadow_height = foreground.offsetHeight;
	shadow.style.width  = (last_shadow_width + shadow_size) + 'px';
	shadow.style.height = (last_shadow_height + shadow_size) + 'px';
      }
    }
    var interval = window.setInterval (function () {
	check_for_frame_message ();
	resize_shadow ();
      }, 50);
    resize_shadow ();
    window.onscroll = function () {
      container.style.top = get_scroll_pos ().y + 'px';
    };
  }

  function image_onmouseover (image, e) {
    var pc = GID ('gls__popup');
    pc.style.display = 'none';
    clear_node (pc);
    var offset = get_offset (image);

    var target = DCE
      ('div', {style: {position: 'absolute',
		       padding: 0, margin: 0,
		       left: (offset.left - outline_size + 1) + 'px',
		       top:  (offset.top - outline_size + 1) + 'px',
		       width:  image.width + 'px',
		       height: image.height + 'px',
		       border: outline_size + 'px solid #1030cc',
		       cursor: 'pointer'}},
	['<div style="margin:0; padding:0; width:100%; height:100%; position:relative; z-index:1; background-color:white; filter:alpha(opacity=1); opacity: 0.01"></div><div style="margin:0; position:absolute; top:0; left:0; background-color:white; padding:3px; color:#1030cc; border: 1px solid #1030cc; border-width: 0px 1px 1px 0px; z-index:2">' + '{% trans "Share image" %}' + '</div>']);
    pc.appendChild (target);

    addEventListener (target, 'click', curry (image_onclick, image));
    addEventListener (target, 'mouseout', hover_onmouseout);

    pc.style.display = '';
    cancelEvent (e);
  }

  function hover_onmouseout (e) {
    var pc = GID ('gls__popup');
    if (!pc) return;
    for (var n = e.toElement || e.relatedTarget; n; n = n.parentNode)
      if (n == pc) return; /* moused over child */
    clear_node (pc);
    pc.style.display = 'none';
    cancelEvent (e);
  }

  function image_onclick (image, e) {
    cancelEvent (e);
    send_frame_message ({image: image.src, w: image.width, h: image.height});
  }

  function addEventListener (obj, event_name, listener) {
    var fn = listener;
    if (obj.addEventListener) {
      obj.addEventListener (event_name, fn, false);
    }
    else if (obj.attachEvent) {
      fn = function () { listener (window.event); };
      obj.attachEvent ('on' + event_name, fn);
    }
    else {
      throw new Error ('Event registration is not supported');
    }
    return {
      instance: obj,
      name: event_name,
      listener: fn
    };
  }

  function removeEventListener (event) {
    var ins = event.instance;
    if (ins.removeEventListener)
      ins.removeEventListener (event.name, event.listener, false);
    else if (ins.detachEvent)
      ins.detachEvent ('on' + event.name, event.listener);
  }

  function cancelEvent (e) {
    if (!e) e = window.event;
    if (e.preventDefault)
      e.preventDefault ();
    else
      e.returnValue = false;
  }

  function get_offset (obj) {
    var curleft = 0;
    var curtop = 0;
    if (obj.offsetParent) {
      curleft = obj.offsetLeft;
      curtop = obj.offsetTop;
      while (obj = obj.offsetParent) {
	curleft += obj.offsetLeft;
	curtop += obj.offsetTop;
      }
    }
    return {
      left: curleft,
      top: curtop
    };
  }

  function get_scroll_pos () {
    if (self.pageYOffset !== undefined) {
      return {
        x: self.pageXOffset,
	y: self.pageYOffset
      };
    }
    var d = document.documentElement;
    return {
      x: d.scrollLeft,
      y: d.scrollTop
    };
  }

  function set_scroll_pos (pos) {
    var e = document.documentElement;
    var b = document.body;
    e.scrollLeft = b.scrollLeft = pos.x;
    e.scrollTop = b.scrollTop = pos.y;
  }

  function clear_node (node) {
    while (node.firstChild)
      node.removeChild (node.firstChild);
  }

  function remove_node (node) {
    if (node && node.parentNode)
      node.parentNode.removeChild (node);
  }

  function remove_container () {
    remove_node (GID ('gls__container'));
    return false;
  }

  function curry (method) {
    var curried = [];
    for (var i = 1; i < arguments.length; i++)
      curried.push (arguments[i]);
    return function () {
      var args = [];
      for (var i = 0; i < curried.length; i++)
	args.push (curried[i]);
      for (var i = 0; i < arguments.length; i++)
	args.push (arguments[i]);
      return method.apply (null, args);
    }
  }

  function GID (id) {
    return document.getElementById (id);
  }

  function send_frame_message (m) {
    var p = '';
    for (var i in m) {
      if (!m.hasOwnProperty (i))
	continue;
      p += (p.length ? '&' : '');
      p += encodeURIComponent (i) + '=' + encodeURIComponent (m[i]);
    }

    if (navigator.userAgent.indexOf ('Safari') != -1)
      var iframe = frames['gls__iframe'];
    else
      var iframe = GID ('gls__iframe').contentWindow;

    if (!iframe) return;
    var url = '{{ page.base_url }}/bookmarklet/frame#' + p;
    try {
      iframe.location.replace (url);
    }
    catch (e) {
      iframe.location = url; /* Safari */
    }
  }

  var current_scroll = get_scroll_pos ();

  function check_for_frame_message () {
    var prefix = 'GLSSHARE-';
    var hash = location.href.split ('#')[1]; /* location.hash is decoded */
    if (!hash || hash.substring(0, prefix.length) != prefix) {
      current_scroll = get_scroll_pos (); /* save position */
      return;
    }
    location.replace (location.href.split ('#')[0] + '#');
    handle_message (hash);
    var pos = current_scroll;
    set_scroll_pos (pos);
    setTimeout (function () { set_scroll_pos (pos); }, 10);
  }

  function handle_message (msg) {
    msg = msg.split ('-');
    for (var i = 0; i < msg.length; i++)
      msg[i] = decodeURIComponent (msg[i]);
    switch (msg[1]) {
    case 'close':
      close (msg.slice (2));
      break;
    case 'frameh':
      GID ('gls__foreground').style.height = msg[2] + 'px';
      break;
    }
  }

  function close (args) {
    window.onscroll = null;
    for (var i = 0; i < available_images.length; i++)
      removeEventListener (available_images[i].listener);
    remove_node (GID ('gls__popup'));
    if (!args || !args.length) {
      remove_container ();
      return;
    }
    var message = args[0].replace ('<a ', '<a style="font-weight:bold; color:#1030cc;" ');
    var fg = GID ('gls__foreground');
    clear_node (fg);
    fg.style.color = 'black';
    fg.style.padding = '4px 10px 4px 4px';
    fg.style.font = '10pt Arial, sans-serif';
    fg.style.fontStyle  = 'normal';
    fg.style.fontWeight = 'normal';
    fg.style.width  = '';
    fg.style.height = '';
    fg.innerHTML = '<img style="width:16px; height:16px; margin-bottom:-3px; margin-right:1px;" src="{{ page.base_url }}/favicon.ico"> '+ message +' <a href="#" id="gls__close" style="margin-left:1em; color:#1030cc;">'+ '{% trans "Close" %}' +'</a>';
    GID ('gls__close').onclick = remove_container;
    setTimeout (remove_container, 5000);
  }

  if (document.getElementsByTagName ('head').length == 0 ||
      frames.length > document.getElementsByTagName ('iframe').length) {
    window.location.href = '{{ page.base_url }}/?link=' + escape (window.location.href);
  }
  else {
    bookmarklet ();
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
