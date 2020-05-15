# -*- coding: utf-8 -*-
# Copyright (c) 2020  Red Hat, Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Written by Jan Kaluza <jkaluza@redhat.com>


from flask.views import MethodView
from flask import request, jsonify

from cts import app, conf, version
from cts.errors import NotFound
from cts.models import Compose
from cts.api_utils import pagination_metadata, filter_composes
from cts.auth import requires_role, login_required, require_scopes


api_v1 = {
    'composes': {
        'url': '/api/1/composes/',
        'options': {
            'defaults': {'id': None},
            'methods': ['GET'],
        }
    },
    'compose': {
        'url': '/api/1/composes/<int:id>',
        'options': {
            'methods': ['GET'],
        }
    },
    'composes_post': {
        'url': '/api/1/composes/',
        'options': {
            'methods': ['POST'],
        }
    },
    'about': {
        'url': '/api/1/about/',
        'options': {
            'methods': ['GET']
        }
    },
}


class CTSAPI(MethodView):
    def get(self, id):
        """ Returns CTS composes.

        If ``id`` is set, only the compose defined by that ID is
        returned.

        :query string id: Return only compose with this :ref:`id<id>`.
        :query string order_by: Order the composes by the given field. If ``-`` prefix is used,
            the order will be descending. The default value is ``-id``.
        :statuscode 200: Composes are returned.
        :statuscode 404: Compose not found.
        """
        if id is None:
            p_query = filter_composes(request)

            json_data = {
                'meta': pagination_metadata(p_query, request.args),
                'items': [item.json() for item in p_query.items]
            }

            return jsonify(json_data), 200

        else:
            compose = Compose.query.filter_by(id=id).first()
            if compose:
                return jsonify(compose.json(True)), 200
            else:
                raise NotFound('No such compose found.')

    @login_required
    @require_scopes('new-compose')
    @requires_role('allowed_clients')
    def post(self):
        """ Adds new compose to CTS database.

        :statuscode 200: Compose request created and returned.
        :statuscode 401: Request not in valid format.
        :statuscode 401: User is unathorized.
        """
        # TODO: Write it.
        return jsonify({}), 200


class AboutAPI(MethodView):
    def get(self):
        """ Returns information about this CTS instance in JSON format.

        :resjson string version: The CTS server version.
        :resjson string auth_backend: The name of authorization backend this
            server is configured with. Can be one of following:

            - ``noauth`` - No authorization is required.
            - ``kerberos`` - Kerberos authorization is required.
            - ``openidc`` - OpenIDC authorization is required.
            - ``kerberos_or_ssl`` - Kerberos or SSL authorization is required.
            - ``ssl`` - SSL authorization is required.
        :statuscode 200: Compose updated and returned.
        """
        json = {'version': version}
        config_items = ['auth_backend']
        for item in config_items:
            config_item = getattr(conf, item)
            # All config items have a default, so if doesn't exist it is
            # an error
            if config_item is None:
                raise ValueError(
                    'An invalid config item of "%s" was specified' % item)
            json[item] = config_item
        return jsonify(json), 200


def register_api_v1():
    """ Registers version 1 of CTS API. """
    composes_view = CTSAPI.as_view('composes')
    about_view = AboutAPI.as_view('about')
    for key, val in api_v1.items():
        if key.startswith("compose"):
            app.add_url_rule(val['url'],
                             endpoint=key,
                             view_func=composes_view,
                             **val['options'])
        elif key.startswith("about"):
            app.add_url_rule(val['url'],
                             endpoint=key,
                             view_func=about_view,
                             **val['options'])
        else:
            raise ValueError("Unhandled API key: %s." % key)


register_api_v1()
