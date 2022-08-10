=========
CTS APIs
=========

HTTP REST API
=============

The API documentation is available at **/api/1/** of your CTS instance since *v1.0.0*.

*openapispec.json* file is required to render the doc.

For local dev env you can generate it by:

.. sourcecode:: none

    $ cts-manager openapispec > cts/static/openapispec.json

For production env running via httpd for example, `openapispec.json` should be served at `/static/openapispec.json` via httpd.


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
        'compose': COMPOSE_JSON,
        'agent': 'username'
    }

Topic: cts.compose-untagged
---------------------------

Compose tag has been removed from the Compose. Message body:

.. sourcecode:: none

    {
        'event': 'compose-untagged',
        'tag': 'some_tag',
        'compose': COMPOSE_JSON,
        'agent': 'username'
    }

    
