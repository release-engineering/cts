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
import os

from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from apispec_webframeworks.flask import FlaskPlugin
from productmd import ComposeInfo
from flask.views import MethodView, View
from flask import render_template, request, jsonify, g, Response
from flask_login import login_required
from marshmallow import Schema, fields
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy.exc import IntegrityError

from cts import app, conf, version, db
from cts.errors import NotFound, Forbidden
from cts.models import Compose, Tag
from cts.api_utils import pagination_metadata, filter_composes, filter_tags
from cts.auth import requires_role, require_scopes, has_role
from cts.metrics import registry


app.openapispec = APISpec(
    title="Compose Tracking Service (CTS)",
    version="v1",
    openapi_version="3.0.2",
    plugins=[FlaskPlugin(), MarshmallowPlugin()],
)


class MetaSchema(Schema):
    """Schema for paginated response."""

    first = fields.URL()
    last = fields.URL()
    next = fields.URL()
    pre = fields.URL()
    page = fields.Integer()
    pages = fields.Integer()
    per_page = fields.Integer()
    total = fields.Integer()


class ComposeInfoHeaderSchema(Schema):
    type = fields.String()
    version = fields.String()


class ComposeInfoPayloadBaseproductSchema(Schema):
    name = fields.String()
    short = fields.String()
    type = fields.String()
    version = fields.String()


class ComposeInfoPayloadComposeSchema(Schema):
    date = fields.Date()
    final = fields.Boolean()
    id = fields.String()
    label = fields.String()
    respin = fields.Integer()
    type = fields.String()


class ComposeInfoPayloadReleaseSchema(Schema):
    internal = fields.Boolean()
    is_layered = fields.Boolean()
    name = fields.String()
    short = fields.String()
    type = fields.String()
    version = fields.String()


class ComposeInfoPayloadSchema(Schema):
    base_product = fields.Nested(ComposeInfoPayloadBaseproductSchema())
    compose = fields.Nested(ComposeInfoPayloadComposeSchema())
    release = fields.Nested(ComposeInfoPayloadReleaseSchema())
    variants = fields.Dict()


class ComposeInfoSchema(Schema):
    """Schema for productmd.ComposeInfo object."""

    header = fields.Nested(ComposeInfoHeaderSchema())
    payload = fields.Nested(ComposeInfoPayloadSchema())


class ComposeSchema(Schema):
    """Schema for ComposeDetailAPI response."""

    builder = fields.String()
    children = fields.List(fields.String())
    compose_info = fields.Nested(ComposeInfoSchema())
    compose_url = fields.URL()
    parents = fields.List(fields.String())
    respin_of = fields.String()
    respun_by = fields.List(fields.String())
    tags = fields.List(fields.String())


class ComposeListSchema(Schema):
    """Schema for ComposesListAPI response."""

    items = fields.List(fields.Nested(ComposeSchema))
    meta = fields.Nested(MetaSchema)


class TagSchema(Schema):
    """Schema for TagDetailAPI response."""

    description = fields.String()
    documentation = fields.String()
    id = fields.Integer()
    name = fields.String()
    taggers = fields.List(fields.String())
    untaggers = fields.List(fields.String())


class TagListSchema(Schema):
    """Schema for TagsListAPI response."""

    items = fields.List(fields.Nested(TagSchema))
    meta = fields.Nested(MetaSchema)


class HTTPErrorSchema(Schema):
    """Schema for 401, 403, 404 error response."""

    error = fields.String()
    message = fields.String()
    status = fields.Integer()


class ComposesListAPI(MethodView):
    def get(self):
        """Returns CTS composes.

        ---
        summary: List composes
        description: |
          It is possible to query for substrings by using following suffixes
          for each query parameter of string type:

          - `*_contains` - The value of this field contains the substring.
          - `*_startswith` - The value of this field starts with this substring.
          - `*_endswith` - The value of this field ends with this substring.

          For example, to return only Alpha composes: `label_startswith=Alpha`.
        parameters:
          - name: date
            in: query
            schema:
              type: string
            required: false
            description: Return only composes with this ComposeInfo date value.
          - name: date_before
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with date before given date
          - name: date_after
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with date after given date
          - name: respin
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo respin value.
          - name: type
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo type value.
          - name: label
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo label value.
          - name: final
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo final value.
          - name: release_name
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo release name value.
          - name: release_version
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo release version value.
          - name: release_short
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo release short value.
          - name: release_is_layered
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo release is_layered value.
          - name: release_type
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo release type value.
          - name: release_internal
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo release internal value.
          - name: base_product_name
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo base_product name value.
          - name: base_product_short
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo base_product short value.
          - name: base_product_version
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo base_product version value.
          - name: base_product_type
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes with this ComposeInfo base_product type value.
          - name: builder
            in: query
            schema:
              type: string
            rquired: false
            description: Return only composes imported by this builder username.
          - name: tag
            in: query
            schema:
              type: string
            rquired: false
            description: |
              Return only composes tagged by one of these tags. Use empty value (``?tag=``)
              to get composes with no tag, or prefix the tag name with ``-`` to get composes
              not tagged with this tag.
          - name: order_by
            in: query
            schema:
              type: string
            rquired: false
            description: |
              Order the composes by the given fields. If ``-`` prefix is used,
              the order will be descending. This query can be used multi time.
              The default value is `?order_by=-date&order_by=-id`.
        responses:
          200:
            content:
              application/json:
                schema: ComposeListSchema
        """
        p_query = filter_composes(request)

        json_data = {
            "meta": pagination_metadata(p_query, request.args),
            "items": [item.json() for item in p_query.items],
        }

        return jsonify(json_data), 200

    @login_required
    @require_scopes("new-compose")
    @requires_role("allowed_builders")
    def post(self):
        """Add new compose to CTS.

        ---
        summary: Add compose
        description: Add new compose to CTS.
        requestBody:
          content:
            application/json:
              schema:
                type: object
                properties:
                  compose_info:
                    type: object
                    description: |
                      `Required`. Compose metadata in `productmd.ComposeInfo` format.
                      Refer to https://productmd.readthedocs.io/en/latest/composeinfo-1.1.html
                  parent_compose_ids:
                    type: array of string
                    description: Compose IDs of parent composes associated with this compose.
                  respin_of:
                    type: string
                    description: Compose ID of the original compose which this compose respins.
                  compose_url:
                    type: string
                    description: URL to the top level directory of this compose.
        responses:
          200:
            description: Compose request created and updated ComposeInfo returned.
            content:
              application/json:
                schema: ComposeSchema
          400:
            description: Request not in valid format.
            content:
              application/json:
                schema: HTTPErrorSchema
          401:
            description: User is unathorized.
            content:
              text/html:
                schema:
                  type: string
          403:
            description: User is not allowed to add compose.
            content:
              application/json:
                schema: HTTPErrorSchema
        """
        data = request.get_json(force=True)
        if not data:
            raise ValueError("No JSON POST data submitted")

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
        compose_url = data.get("compose_url", None)

        ci = Compose.create(
            db.session,
            g.user.username,
            ci,
            parent_compose_ids=parent_compose_ids,
            respin_of=respin_of,
            compose_url=compose_url,
        )[1]
        return jsonify(json.loads(ci.dumps())), 200


class ComposeDetailAPI(MethodView):
    def get(self, id):
        """Returns compose.

        ---
        summary: Get compose
        description: |
          Get single compose by compose id. It returns compose in json format, for example:

              {
                  "builder": "odcs",
                  "tags": ["periodic"],
                  "parents": ["Fedora-Base-20200517.n.1"]
                  "children": [],
                  "respin_of": None,
                  "respun_by": [],
                  "compose_url": "http://localhost/compose/Fedora-Rawhide-bp-Rawhide-20200517.n.1",
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
        parameters:
          - name: id
            in: path
            schema:
              type: string
            required: true
            description: Compose ID
        responses:
          200:
            content:
              application/json:
                schema: ComposeSchema
          404:
            description: Compose not found.
            content:
              application/json:
                schema: HTTPErrorSchema
        """
        compose = Compose.query.filter_by(id=id).first()
        if compose:
            return jsonify(compose.json(True)), 200
        else:
            raise NotFound("No such compose found.")

    @login_required
    @require_scopes("edit-compose")
    def patch(self, id):
        """Change the compose metadata.

        ---
        summary: Edit compose
        description: Change the compose metadata.
        requestBody:
          content:
            application/json:
              schema:
                type: object
                properties:
                  action:
                    type: string
                    enum:
                      - tag
                      - untag
                      - set_url
                    description: |
                      `Required`. One of the action
                      - ``tag`` - Add ``tag`` to compose.
                      - ``untag`` - Remove ``tag`` from compose.
                      - ``set_url`` - Update compose_url.
                  tag:
                    type: string
                    description: Tag to use.
                  user_data:
                    type: string
                    description: |
                      Optional data stored in the compose change history for
                      this compose change. For example URL to ticket requesting
                      this compose change.
                  compose_url:
                    type: string
                    description: URL to the top level directory of the compose.
        responses:
          200:
            description: Compose updated and returned.
            content:
              application/json:
                schema: ComposeSchema
          401:
            description: User is unathorized.
            content:
              text/html:
                schema:
                  type: string
          403:
            description: User is not allowed to edit compose.
            content:
              application/json:
                schema: HTTPErrorSchema
          404:
            description: Compose not found.
            content:
              application/json:
                schema: HTTPErrorSchema
        """
        compose = Compose.query.filter_by(id=id).first()
        if not compose:
            raise NotFound("No such compose found.")

        data = request.get_json(force=True)
        if not data:
            raise ValueError("No JSON PATCH data submitted.")

        action = data.get("action", None)
        if action is None:
            raise ValueError('No "action" field in JSON PATCH data.')

        user_data = data.get("user_data", None)

        is_admin = has_role("admins")

        if action in ["tag", "untag"]:
            tag_name = data.get("tag", None)
            if not tag_name:
                raise ValueError('No "tag" field in JSON PATCH data.')
            tag = Tag.get_by_name(tag_name)
            if not tag:
                raise ValueError('Tag "%s" does not exist' % tag_name)

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
        elif action == "set_url":
            if not has_role("allowed_builders") and not is_admin:
                raise Forbidden(
                    'User "%s" does not have permission to set compose_url'
                    % g.user.username
                )

            compose_url = data.get("compose_url", None)
            if compose_url is None:
                raise ValueError('No "compose_url" field in JSON PATCH data.')
            if not compose_url.startswith("http"):
                raise ValueError('"compose_url" field must be a valid http(s) URL')
            compose.compose_url = compose_url
        else:
            raise ValueError("Unknown action.")

        db.session.commit()
        return jsonify(compose.json()), 200


class AboutAPI(MethodView):
    def get(self):
        """Return information about this CTS instance in JSON format.

        ---
        summary: About
        description: Return information about this CTS instance in JSON format.
        responses:
          200:
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    version:
                      description: The CTS server version.
                      type: string
                    auth_backend:
                      description: |
                        The name of authorization backend this server is configured with.
                        - ``noauth`` - No authorization is required.
                        - ``kerberos`` - Kerberos authorization is required.
                        - ``openidc`` - OpenIDC authorization is required.
                        - ``kerberos_or_ssl`` - Kerberos or SSL authorization is required.
                        - ``ssl`` - SSL authorization is required.
                      type: string
                      enum:
                        - noauth
                        - kerberos
                        - openidc
                        - kerberos_or_ssl
                        - ssl
                    allowed_builders:
                      type: object
        """
        json = {"version": version}
        config_items = ["auth_backend", "allowed_builders"]
        for item in config_items:
            config_item = getattr(conf, item)
            # All config items have a default, so if doesn't exist it is
            # an error
            if config_item is None:
                raise ValueError('An invalid config item of "%s" was specified' % item)
            json[item] = config_item
        return jsonify(json), 200


class MetricsAPI(MethodView):
    def get(self):
        """Returns the Prometheus metrics.

        ---
        summary: Metrics
        description: Returns the Prometheus metrics.
        responses:
          200:
            content:
              text/plain:
                schema:
                  type: string
        """
        return Response(generate_latest(registry), content_type=CONTENT_TYPE_LATEST)


class TagsListAPI(MethodView):
    def get(self):
        """Returns tags.

        ---
        summary: List tags
        description: List tags
        parameters:
          - name: order_by
            in: query
            schema:
              type: string
            required: false
            description: |
              Order the tags by the given fields. If ``-`` prefix is used, the
              order will be descending.
              The default value is `?order_by=-id`.
        responses:
          200:
            content:
              application/json:
                schema: TagListSchema
        """
        p_query = filter_tags(request)

        json_data = {
            "meta": pagination_metadata(p_query, request.args),
            "items": [item.json() for item in p_query.items],
        }

        return jsonify(json_data), 200

    @login_required
    @require_scopes("new-tag")
    @requires_role("admins")
    def post(self):
        """Adds new tag to CTS database.

        ---
        summary: Add tag
        description: Add new tag to CTS.
        requestBody:
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    description: |
                      `Required`. Tag name.
                  description:
                    type: string
                    description: |
                      `Required`. Tag description.
                  documentation:
                    type: string
                    description: |
                      `Required`. Link to full documentation about tag.
                  user_data:
                    type: string
                    description: |
                      `Optional` data stored in the tag change history for this
                      tag change. For example URL to ticket requesting this tag
                      change.
        responses:
          200:
            description: Tag created and returned.
            content:
              application/json:
                schema: TagSchema
          400:
            description: Request not in valid format.
            content:
              application/json:
                schema: HTTPErrorSchema
          401:
            description: User is unathorized.
            content:
              text/html:
                schema:
                  type: string
          403:
            description: User is not allowed to add tag.
            content:
              application/json:
                schema: HTTPErrorSchema
        """
        data = request.get_json(force=True)
        if not data:
            raise ValueError("No JSON POST data submitted.")

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
        try:
            t = Tag.create(
                db.session,
                g.user.username,
                name=name,
                description=description,
                documentation=documentation,
                user_data=user_data,
            )
            db.session.commit()
        except IntegrityError as e:
            if "unique constraint" in str(e).lower():
                raise ValueError("Tag %s already exists" % name)
            raise ValueError(str(e))
        return jsonify(t.json()), 200


class TagDetailAPI(MethodView):
    def get(self, id):
        """Return tag.

        ---
        summary: Get tag
        description: Get tag by numeric `id` or by `tag name` if `id` is string.
        parameters:
          - name: id
            in: path
            schema:
              type: integer or string
            required: true
            description: Numeric ID of the tag or string of tag name to get
        responses:
          200:
            content:
              application/json:
                schema: TagSchema
          404:
            content:
              application/json:
                schema: HTTPErrorSchema
        """
        if id.isdigit():
            tag = Tag.query.filter_by(id=id).first()
        else:
            tag = Tag.query.filter_by(name=id).first()
        if tag:
            return jsonify(tag.json()), 200
        else:
            raise NotFound("No such tag found.")

    @login_required
    @require_scopes("edit-tag")
    @requires_role("admins")
    def patch(self, id):
        """Edit tag.

        ---
        summary: Edit tag
        description: Edit tag name, description, documentation or update taggers/untaggers.
        parameters:
          - name: id
            in: path
            schema:
              type: integer
            required: true
            description: Numeric tag id.
        requestBody:
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    description: Tag `name`. If not set, keep original value.
                  description:
                    type: string
                    description: Tag `description`. If not set, keep original value.
                  documentation:
                    type: string
                    description: Link to full documentation about tag. If not set, keep original value.
                  action:
                    type: string
                    enum:
                      - add_tagger
                      - remove_tagger
                      - add_untagger
                      - remove_untagger
                    description: |
                      Edit action. One of:

                      - ``add_tagger`` - Grant ``tagger`` permission to ``username``.
                      - ``remove_tagger`` - Remove ``tagger`` permission from ``username``.
                      - ``add_untagger`` - Grant ``untagger`` permission to ``username``.
                      - ``remove_untagger`` - Remove ``untagger`` permission from ``username``.

                      If not set, do not edit taggers/untaggers.
                  username:
                    type: string
                    description: Username of tagger/untagger.
                  user_data:
                    type: string
                    description: |
                      Optional data stored in the tag change history for this tag change.
                      For example URL to ticket requesting this tag change.
        responses:
          200:
            description: Tag updated and returned.
            content:
              application/json:
                schema: TagSchema
          401:
            description: User is unathorized.
            content:
              text/html:
                schema:
                  type: string
          403:
            description: User is not allowed to edit tag.
            content:
              application/json:
                schema: HTTPErrorSchema
          404:
            description: Tag not found.
            content:
              application/json:
                schema: HTTPErrorSchema
        """
        t = Tag.query.filter_by(id=id).first()
        if not t:
            raise NotFound("No such tag found.")

        data = request.get_json(force=True)
        if not data:
            raise ValueError("No JSON POST data submitted.")

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
            if action not in [
                "add_tagger",
                "remove_tagger",
                "add_untagger",
                "remove_untagger",
            ]:
                raise ValueError("Unknown action.")
            username = data.get("username", None)
            if not username:
                raise ValueError('"username" is not defined.')
            user_data = data.get("user_data", None)
            r = getattr(t, action)(g.user.username, username, user_data)
            if not r:
                raise ValueError("User does not exist")

        try:
            db.session.commit()
        except IntegrityError as e:
            if "unique constraint" in str(e).lower():
                raise ValueError("Tag %s already exists" % name)
            raise ValueError(str(e))
        return jsonify(t.json()), 200


class RepoAPI(MethodView):
    def get(self, id):
        """Returns content of repofile.

        ---
        summary: Get repo
        description: Return content of repofile
        parameters:
          - name: id
            in: path
            schema:
              type: string
            required: true
            description: Compose ID
          - name: variant
            in: query
            schema:
              type: string
            required: true
            description: Variant name
        responses:
          200:
            content:
              text/plain:
                schema:
                  type: string
        """
        compose = Compose.query.filter_by(id=id).first()
        if not compose:
            raise NotFound("No such compose found.")

        variant = request.args.get("variant")
        if not variant:
            raise ValueError("variant is required.")

        if not compose.compose_url:
            raise NotFound("Compose does not have any URL set")

        baseurl = os.path.join(compose.compose_url, "compose", variant, "$basearch/os/")
        content = """[{compose.id}-{variant}]
name=Compose {compose.id} (RPMs) - {variant}
baseurl={baseurl}
enabled=1
gpgcheck=0
""".format(
            compose=compose, variant=variant, baseurl=baseurl
        )
        return Response(content, content_type="text/plain")


class Index(View):

    methods = ["GET"]

    def dispatch_request(self):
        return render_template("index.html")


class APIDoc(View):

    methods = ["GET"]

    def dispatch_request(self):
        return render_template("apidoc.html")


def register_api_v1():
    """Registers version 1 of CTS API."""
    api_v1 = {
        "composes": {
            "url": "/api/1/composes/",
            "options": {
                "methods": ["GET", "POST"],
            },
            "view_class": ComposesListAPI,
        },
        "composedetail": {
            "url": "/api/1/composes/<id>",
            "options": {
                "methods": ["GET", "PATCH"],
            },
            "view_class": ComposeDetailAPI,
        },
        "tags": {
            "url": "/api/1/tags/",
            "options": {
                "methods": ["GET", "POST"],
            },
            "view_class": TagsListAPI,
        },
        "tagdetail": {
            "url": "/api/1/tags/<id>",
            "options": {
                "methods": ["GET", "PATCH"],
            },
            "view_class": TagDetailAPI,
        },
        "repo": {
            "url": "/api/1/composes/<id>/repo/",
            "options": {
                "methods": ["GET"],
            },
            "view_class": RepoAPI,
        },
        "metrics": {
            "url": "/api/1/metrics/",
            "options": {"methods": ["GET"]},
            "view_class": MetricsAPI,
        },
        "about": {
            "url": "/api/1/about/",
            "options": {"methods": ["GET"]},
            "view_class": AboutAPI,
        },
    }

    for key, val in api_v1.items():
        view_func = val["view_class"].as_view(key)
        app.add_url_rule(
            val["url"], endpoint=key, view_func=view_func, **val["options"]
        )
        with app.test_request_context():
            app.openapispec.path(view=view_func)


app.add_url_rule("/", view_func=Index.as_view("index"))
app.add_url_rule("/api/1/", view_func=APIDoc.as_view("apidoc"))
register_api_v1()
