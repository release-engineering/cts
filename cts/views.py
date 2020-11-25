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

import json
from productmd import ComposeInfo
from flask.views import MethodView
from flask import request, jsonify, g, Response
from flask_login import login_required
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from cts import app, conf, version, db
from cts.errors import NotFound, Forbidden
from cts.models import Compose, Tag
from cts.api_utils import pagination_metadata, filter_composes, filter_tags
from cts.auth import requires_role, require_scopes, has_role
from cts.metrics import registry


api_v1 = {
    'composes': {
        'url': '/api/1/composes/',
        'options': {
            'defaults': {'id': None},
            'methods': ['GET'],
        }
    },
    'compose': {
        'url': '/api/1/composes/<id>',
        'options': {
            'methods': ['GET'],
        }
    },
    'compose_edit': {
        'url': '/api/1/composes/<id>',
        'options': {
            'methods': ['PATCH'],
        }
    },
    'composes_post': {
        'url': '/api/1/composes/',
        'options': {
            'methods': ['POST'],
        }
    },
    'tags': {
        'url': '/api/1/tags/',
        'options': {
            'defaults': {'id': None},
            'methods': ['GET'],
        }
    },
    'tag': {
        'url': '/api/1/tags/<id>',
        'options': {
            'methods': ['GET'],
        }
    },
    'tag_edit': {
        'url': '/api/1/tags/<int:id>',
        'options': {
            'methods': ['PATCH'],
        }
    },
    'tags_post': {
        'url': '/api/1/tags/',
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
    'metrics': {
        'url': '/api/1/metrics/',
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

        :query string id: Return only compose with this ID.
        :query string date: Return only composes with this ComposeInfo date value.
        :query string date_before: Return only composes with date before given date
        :query string date_before: Return only composes with date after given date
        :query string respin: Return only composes with this ComposeInfo respin value.
        :query string type: Return only composes with this ComposeInfo type value.
        :query string label: Return only composes with this ComposeInfo label value.
        :query string final: Return only composes with this ComposeInfo final value.
        :query string release_name: Return only composes with this ComposeInfo release name value.
        :query string release_version: Return only composes with this ComposeInfo release version value.
        :query string release_short: Return only composes with this ComposeInfo release short value.
        :query string release_is_layered: Return only composes with this ComposeInfo release is_layered value.
        :query string release_type: Return only composes with this ComposeInfo release type value.
        :query string release_internal: Return only composes with this ComposeInfo release internal value.
        :query string base_product_name: Return only composes with this ComposeInfo base_product name value.
        :query string base_product_short: Return only composes with this ComposeInfo base_product short value.
        :query string base_product_version: Return only composes with this ComposeInfo base_product version value.
        :query string base_product_type: Return only composes with this ComposeInfo base_product type value.
        :query string builder: Return only composes imported by this builder username.
        :query list tag: Return only composes tagged by one of these tags. Use empty value (``?tag=``)
                         to get composes with no tag, or prefix the tag name with ``-`` to get composes
                         not tagged with this tag.
        :query string/list order_by: Order the composes by the given fields. If ``-`` prefix is used,
            the order will be descending. The default value is ``["-date", "-id"]``.
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
    @requires_role('allowed_builders')
    def post(self):
        """ Adds new compose to CTS database.

        :jsonparam ComposeInfo compose_info: Compose metadata in productmd.ComposeInfo format.
        :jsonparam list parent_compose_ids: Compose IDs of parent composes associated with
            this compose.
        :jsonparam string respin_of: Compose ID of the original compose which this compose
            respins.

        :statuscode 200: Compose request created and updated ComposeInfo returned.
        :statuscode 400: Request not in valid format.
        :statuscode 401: User is unathorized.
        """
        data = request.get_json(force=True)
        if not data:
            raise ValueError('No JSON POST data submitted')

        ci_json = data.get("compose_info", None)
        if ci_json is None:
            raise ValueError('No "compose_info" field in JSON POST data.')

        ci = ComposeInfo()
        try:
            ci.loads(json.dumps(ci_json))
        except Exception as e:
            raise ValueError('Cannot parse "compose_info": %s' % repr(e))

        parent_compose_ids = data.get("parent_compose_ids", None)
        respin_of = data.get("respin_of", None)

        ci = Compose.create(
            db.session, g.user.username, ci, parent_compose_ids=parent_compose_ids,
            respin_of=respin_of
        )[1]
        return jsonify(json.loads(ci.dumps())), 200

    @login_required
    @require_scopes('edit-compose')
    def patch(self, id):
        """ Change the compose metadata.

        :jsonparam str action: One of:

            - ``tag`` - Add ``tag`` to compose.
            - ``untag`` - Remove ``tag`` from compose.
        :jsonparam str tag: Tag to use.
        :jsonparam str user_data: Optional data stored in the compose change history
            for this compose change. For example URL to ticket requesting this compose
            change.

        :statuscode 200: Compose updated and returned.
        :statuscode 401: User is unathorized for this change.
        :statuscode 404: Compose not found.
        """
        compose = Compose.query.filter_by(id=id).first()
        if not compose:
            raise NotFound('No such compose found.')

        data = request.get_json(force=True)
        if not data:
            raise ValueError('No JSON PATCH data submitted.')

        action = data.get("action", None)
        if action is None:
            raise ValueError('No "action" field in JSON PATCH data.')

        user_data = data.get("user_data", None)

        if action in ["tag", "untag"]:
            tag_name = data.get("tag", None)
            if not tag_name:
                raise ValueError('No "tag" field in JSON PATCH data.')
            tag = Tag.get_by_name(tag_name)
            if not tag:
                raise ValueError('Tag "%s" does not exist' % tag_name)

            is_admin = has_role("admins")
            if action == "tag":
                if g.user not in tag.taggers and not is_admin:
                    raise Forbidden(
                        'User "%s" does not have "taggers" permission for tag '
                        '"%s".' % (g.user.username, tag_name)
                    )
                compose.tag(g.user.username, tag_name, user_data)
            else:
                if g.user not in tag.untaggers and not is_admin:
                    raise Forbidden(
                        'User "%s" does not have "taggers" permission for tag '
                        '"%s".' % (g.user.username, tag_name)
                    )
                compose.untag(g.user.username, tag_name, user_data)
        else:
            raise ValueError("Unknown action.")

        db.session.commit()
        return jsonify(compose.json()), 200


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


class MetricsAPI(MethodView):
    def get(self):
        """
        Returns the Prometheus metrics.

        :statuscode 200: Prometheus metrics returned.
        """
        return Response(generate_latest(registry), content_type=CONTENT_TYPE_LATEST)


class TagAPI(MethodView):
    def get(self, id):
        """ Returns tags.

        If ``id`` is set, only the tag defined by that ID is
        returned. If ``id`` is string, it is treated as tag name.

        :query string id: Return only tag with this :ref:`id<tag_id>` or :ref:`name<tag_name>`.
        :query string/list order_by: Order the tags by the given fields. If ``-`` prefix is used,
            the order will be descending. The default value is ``["-id"]``.
        :statuscode 200: Tags are returned.
        :statuscode 404: Tag not found.
        """
        if id is None:
            p_query = filter_tags(request)

            json_data = {
                'meta': pagination_metadata(p_query, request.args),
                'items': [item.json() for item in p_query.items]
            }

            return jsonify(json_data), 200

        else:
            if id.isdigit():
                tag = Tag.query.filter_by(id=id).first()
            else:
                tag = Tag.query.filter_by(name=id).first()
            if tag:
                return jsonify(tag.json()), 200
            else:
                raise NotFound('No such tag found.')

    @login_required
    @require_scopes('new-tag')
    @requires_role('admins')
    def post(self):
        """ Adds new tag to CTS database.

        :jsonparam str name: Tag name.
        :jsonparam str description: Tag description.
        :jsonparam str documentation: Link to full documentation about tag.
        :jsonparam str user_data: Optional data stored in the tag change history
            for this tag change. For example URL to ticket requesting this tag
            change.

        :statuscode 200: Tag created and returned.
        :statuscode 400: Request not in valid format.
        :statuscode 401: User is unathorized.
        """
        data = request.get_json(force=True)
        if not data:
            raise ValueError('No JSON POST data submitted.')

        name = data.get("name", None)
        if not name:
            raise ValueError('Tag "name" is not defined.')

        description = data.get("description", None)
        if not description:
            raise ValueError('Tag "description" is not defined.')

        documentation = data.get("documentation", None)
        if not documentation:
            raise ValueError('Tag "documentation" is not defined.')

        user_data = data.get("user_data", None)
        t = Tag.create(
            db.session, g.user.username, name=name, description=description,
            documentation=documentation, user_data=user_data
        )
        db.session.commit()
        return jsonify(t.json()), 200

    @login_required
    @require_scopes('edit-tag')
    @requires_role('admins')
    def patch(self, id):
        """ Edit tag.

        :query number id: :ref:`ID<tag_id>` of the tag to edit.
        :jsonparam str name: Tag :ref:`name<tag_name>`. If not set, keep original value.
        :jsonparam str description: Tag :ref:`description<tag_description>`. If not set, keep original value.
        :jsonparam str documentation: Link to full :ref:`documentation<tag_documentation>` about tag.
            If not set, keep original value.
        :jsonparam str action: Edit action. One of:

            - ``add_tagger`` - Grant ``tagger`` permission to ``username``.
            - ``remove_tagger`` - Remove ``tagger`` permission from ``username``.
            - ``add_untagger`` - Grant ``untagger`` permission to ``username``.
            - ``remove_untagger`` - Remove ``untagger`` permission from ``username``.

            If not set, do not edit taggers/untaggers.
        :jsonparam str username: Username of tagger/untagger.
        :jsonparam str user_data: Optional data stored in the tag change history
            for this tag change. For example URL to ticket requesting this tag
            change.

        :statuscode 200: Tag updated and returned.
        :statuscode 401: User is unathorized.
        :statuscode 404: Tag not found.
        """
        t = Tag.query.filter_by(id=id).first()
        if not t:
            raise NotFound('No such tag found.')

        data = request.get_json(force=True)
        if not data:
            raise ValueError('No JSON POST data submitted.')

        name = data.get("name", None)
        if name:
            t.name = name

        description = data.get("description", None)
        if description:
            t.description = description

        documentation = data.get("documentation", None)
        if documentation:
            t.documentation = documentation

        action = data.get("action", None)
        if action:
            if action not in ["add_tagger", "remove_tagger", "add_untagger", "remove_untagger"]:
                raise ValueError("Unknown action.")
            username = data.get("username", None)
            if not username:
                raise ValueError('"username" is not defined.')
            user_data = data.get("user_data", None)
            r = getattr(t, action)(g.user.username, username, user_data)
            if not r:
                raise ValueError('User does not exist')
        db.session.commit()
        return jsonify(t.json()), 200


def register_api_v1():
    """ Registers version 1 of CTS API. """
    composes_view = CTSAPI.as_view('composes')
    tags_view = TagAPI.as_view('tags')
    about_view = AboutAPI.as_view('about')
    metrics_view = MetricsAPI.as_view('metrics')
    for key, val in api_v1.items():
        if key.startswith("compose"):
            app.add_url_rule(val['url'],
                             endpoint=key,
                             view_func=composes_view,
                             **val['options'])
        elif key.startswith("tag"):
            app.add_url_rule(val['url'],
                             endpoint=key,
                             view_func=tags_view,
                             **val['options'])
        elif key.startswith("about"):
            app.add_url_rule(val['url'],
                             endpoint=key,
                             view_func=about_view,
                             **val['options'])
        elif key.startswith("metrics"):
            app.add_url_rule(val['url'],
                             endpoint=key,
                             view_func=metrics_view,
                             **val['options'])
        else:
            raise ValueError("Unhandled API key: %s." % key)


register_api_v1()
