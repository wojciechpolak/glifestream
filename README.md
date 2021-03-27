gLifestream
===========

gLifestream is a free lifestream platform and social activity reader.
It is licensed under GPLv3.

Introduction
------------

gLifestream joins several external and/or internal streams into a
single one.  External streams may be represented by RSS/Atom channels
or popular services such as Twitter.  The user decides which of them
are publicly visible and which are not.  Public streams are visible
for anybody.  The rest of streams are visible only for logged in users.

The gLifestream software requires an HTTP server capable of running
Django applications and a database supported by it.  Data from the
configured streams are automatically pulled from the remote services
associated with them and stored in the database.  This mode of
operation ensures the user that his data (messages, links, photos,
etc.) will remain intact even if the external service they came from
ceases to exist.

To install gLifestream read the INSTALL file.

Supported services (out of the box)
-----------------------------------

Any RSS/Atom feed, Flickr, Twitter, Vimeo, YouTube.

Any service not listed above can be added as an RSS/Atom stream (if it
provides such feeds) or by extending gLifestream and writing custom
APIs support.

Features
--------

- Free, self-hosted web application
- Automatic imports of external streams
- Public and Private views
- User views: Favorite entries, Archives, custom stream lists
- Automatic expansion of shortened URLs
- Embedded multimedia views
- Out of the box output formats: HTML5, Atom, JSON
- Search functionality
- PubSubHubbub support (publisher and subscriber)
- OAuth support
- Write posts by web or e-mail (including media attachments)
- Keyboard shortcuts for navigation
- Customizable themes
- Bookmarklet for easy webpage sharing
- Localization
