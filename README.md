gLifestream
===========

gLifestream is a free lifestream platform and social activity reader.
It is licensed under GPLv3.

Introduction
------------

gLifestream joins several external and/or internal streams into a
single one.  External streams may be represented by RSS/Atom channels
or popular services such as Mastodon.  The user decides which of them
are publicly visible and which are not.  Public streams are visible
for anybody.  The rest of streams are visible only for logged in users.

The gLifestream software requires an HTTP server capable of running
Django applications and a database supported by it.  Data from the
configured streams are automatically pulled from the remote services
associated with them and stored in the database.  This mode of
operation ensures the user that his data (messages, links, photos,
etc.) will remain intact even if the external service they came from
ceases to exist.

To install gLifestream read the [INSTALL](INSTALL.md) file.

Supported services (out of the box)
-----------------------------------

gLifestream supports the following services by default:

- Any RSS/Atom feed
- Mastodon
- Bluesky
- Flickr
- PixelFed
- Pocket
- Twitter
- Vimeo
- YouTube

You can extend gLifestream by writing custom APIs
to support additional services.

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
- WebSub support (publisher and subscriber)
- OAuth 1.0 and 2.0 support
- Write posts by web or e-mail (including media attachments)
- Keyboard shortcuts for navigation
- Customizable themes
- Localization
