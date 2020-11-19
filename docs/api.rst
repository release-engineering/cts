=========
CTS APIs
=========

.. _compose_json:

CTS Compose JSON representation
===============================

The CTS Compose is always represented in the API requests as JSON, for example:

.. sourcecode:: none

    {
        "builder": "odcs",
        "tags": ["periodic"],
        "parents": ["Fedora-Base-20200517.n.1"]
        "children": [],
        "respin_of": None,
        "respun_by": [],
        "compose_info": {
            "header": {
                "type": "productmd.composeinfo",
                "version": "1.2"
            },
            "payload": {
                "compose": {
                    "date": "20200517",
                    "id": "Fedora-Rawhide-bp-Rawhide-20200517.n.1",
                    "respin": 1,
                    "type": "nightly"
                },
                "release": {
                    "internal": False,
                    "name": "Fedora",
                    "short": "Fedora",
                    "type": "ga",
                    "version": "Rawhide",
                    "is_layered": True,
                },
                "base_product": {
                    "name": "base-product",
                    "short": "bp",
                    "type": "ga",
                    "version": "Rawhide",
                },
                "variants": {}
            }
        }
    }

The fields used in the CTS compose JSON have following meaning:

.. _compose_builder:

*builder* - ``(string)``
    Name of the user (service) who built the compose.

.. _compose_tags:

*tags* - ``(list of strings)``
    List of compose tags.

.. _compose_compose_info:

*compose_info* - ``(productmd.ComposeInfo)``
    Compose metadata in https://productmd.readthedocs.io/en/latest/composeinfo-1.1.html format.

.. _compose_parents:

*parents* - ``(list of strings)``
    Compose IDs of parent composes. The parent composes can be set using the ``parent_compose_ids`` argument when creating the compose.

.. _compose_children:

*children* - ``(list of strings)``
    Compose IDs of child composes.

.. _compose_respin_of:

*respin_of* - ``(string)``
    Compose IDs of compose this compose respins. Can be set using the ``respin_of`` argument when creating the compose.

.. _compose_respun_by:

*respun_by* - ``(list of strings)``
    Compose IDs of composes respinning this compose.


CTS Compose Tag JSON representation
===================================

The CTS Compose Tag is always represented in the API requests as JSON, for example:

.. sourcecode:: none

    {
        "id": 1,
        "name": "periodic",
        "description": "Periodic compose",
        "documentation": "http://localhost/",
        "taggers": ["me", "you"],
        "untaggers": ["me"]
    }

.. _tag_id:

*id* - ``(number)``
    ID of the Compose Tag.

.. _tag_name:

*name* - ``(string)``
    Name of the Compose Tag.

.. _tag_description:

*description* - ``(string)``
    Short description of the tag.

.. _tag_documentation:

*documentation* - ``(string)``
    Link to full documentation for this Compose Tag.

.. _tag_taggers:

*taggers* - ``(list of strings)``
    List of users (services) who can tag compose using this Compose Tag.

.. _tag_untaggers:

*untaggers* - ``(list of strings)``
    List of users (services) who can remove this Compose Tag from compose.

REST API pagination
===================

When multiple objects (Composes or Compose tags) are returned by the CTS REST API, they are wrapped in the following JSON which allows pagination. For exaample:

.. sourcecode:: none

    {
        "items": [
            {compose_json},
            ...
        ],
        "meta": {
            "first": "http://cts.localhost/api/1/composes/?per_page=10&page=1",
            "last": "http://cts.localhost/api/1/composes/?per_page=10&page=14890",
            "next": "http://cts.localhost/api/1/composes/?per_page=10&page=2",
            "page": 1,
            "pages": 14890,
            "per_page": 10,
            "prev": null,
            "total": 148898
        }
    }

The ``items`` list contains the CTS objects JSONs. The ``meta`` dict contains metadata about pagination. It is possible to use ``per_page`` argument to set the number of objects showed per single page and ``page`` to choose the page to show.

.. _http-api:

HTTP REST API
=============

.. automodule:: cts

.. autoflask:: cts:app
    :undoc-static:
    :modules: cts.views
    :order: path


Messaging API
=============

CTS also sends AMQP or fedora-messaging messages when Compose changes.

Topic: cts.compose-created
--------------------------

New compose has been added to CTS. This is usually done before the compose build starts. Message body:

.. sourcecode:: none

    {
        'event': 'compose-created',
        'compose': COMPOSE_JSON
    }


Topic: cts.compose-tagged
--------------------------

Compose tag has been added to the Compose. Message body:

.. sourcecode:: none

    {
        'event': 'compose-tagged',
        'tag': 'some_tag',
        'compose': COMPOSE_JSON
    }

Topic: cts.compose-untagged
---------------------------

Compose tag has been removed from the Compose. Message body:

.. sourcecode:: none

    {
        'event': 'compose-untagged',
        'tag': 'some_tag',
        'compose': COMPOSE_JSON
    }

    
