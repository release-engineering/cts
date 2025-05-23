# -*- coding: utf-8 -*-
# Copyright (c) 2017  Red Hat, Inc.
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

from flask import request, url_for
from sqlalchemy import cast, func, ARRAY, Integer
from sqlalchemy.orm import selectinload

from cts.models import Compose, Tag


def pagination_metadata(p_query, request_args):
    """
    Returns a dictionary containing metadata about the paginated query.
    This must be run as part of a Flask request.
    :param p_query: flask_sqlalchemy.Pagination object
    :param request_args: a dictionary of the arguments that were part of the
    Flask request
    :return: a dictionary containing metadata about the paginated query
    """

    request_args_wo_page = request_args.to_dict(flat=False)
    # Remove pagination related args because those are handled elsewhere
    # Also, remove any args that url_for accepts in case the user entered
    # those in
    for key in ["page", "per_page", "endpoint"]:
        if key in request_args_wo_page:
            request_args_wo_page.pop(key)
    for key in request_args:
        if key.startswith("_"):
            request_args_wo_page.pop(key)
    pagination_data = {
        "page": p_query.page,
        "pages": p_query.pages,
        "per_page": p_query.per_page,
        "prev": None,
        "next": None,
        "total": p_query.total,
        "first": url_for(
            request.endpoint,
            page=1,
            per_page=p_query.per_page,
            _external=True,
            **request_args_wo_page
        ),
        "last": url_for(
            request.endpoint,
            page=p_query.pages,
            per_page=p_query.per_page,
            _external=True,
            **request_args_wo_page
        ),
    }

    if p_query.has_prev:
        pagination_data["prev"] = url_for(
            request.endpoint,
            page=p_query.prev_num,
            per_page=p_query.per_page,
            _external=True,
            **request_args_wo_page
        )

    if p_query.has_next:
        pagination_data["next"] = url_for(
            request.endpoint,
            page=p_query.next_num,
            per_page=p_query.per_page,
            _external=True,
            **request_args_wo_page
        )

    return pagination_data


def _order_by(flask_request, query, base_class, allowed_keys, default_keys):
    """
    Parses the "order_by" argument from flask_request.args, checks that
    it is allowed for ordering in `allowed_keys` list and sets the ordering
    in the `query`.
    In case "order_by" is not set in flask_request.args, use `default_keys`
    instead.

    If "order_by" argument starts with minus sign ('-'), the descending order
    is used.
    """
    order_by_list = flask_request.args.getlist("order_by") or default_keys

    # Handle empty "?order_by=" request and use default ordering in this case.
    if "" in order_by_list:
        order_by_list = default_keys

    for order_by in order_by_list:
        if order_by and len(order_by) > 1 and order_by[0] == "-":
            order_asc = False
            order_by = order_by[1:]
        else:
            order_asc = True

        if order_by not in allowed_keys:
            raise ValueError(
                "An invalid order_by key was suplied, allowed keys are: "
                "%r" % allowed_keys
            )

        order_by_attr = getattr(base_class, order_by)
        if order_by == "release_version":
            order_by_attr = cast(
                func.string_to_array(
                    func.regexp_replace(order_by_attr, "[^0-9.]", "", "g"), "."
                ),
                ARRAY(Integer),
            )
        if not order_asc:
            order_by_attr = order_by_attr.desc()
        query = query.order_by(order_by_attr)
    return query


def filter_composes(flask_request):
    """
    Returns a flask_sqlalchemy.Pagination object based on the request parameters
    :param request: Flask request object
    :return: flask_sqlalchemy.Pagination
    """
    search_query = dict()

    allowed_keys = [
        "id",
        "date",
        "respin",
        "type",
        "label",
        "final",
        "release_name",
        "release_version",
        "release_short",
        "release_is_layered",
        "release_type",
        "release_internal",
        "base_product_name",
        "base_product_short",
        "base_product_version",
        "base_product_type",
        "builder",
    ]
    allowed_suffixes = ["", "_contains", "_startswith", "_endswith"]
    for key in allowed_keys:
        for suffix in allowed_suffixes:
            if flask_request.args.get(key + suffix, None):
                search_query[key] = (flask_request.args[key + suffix], suffix)

    query = Compose.query
    query = query.options(
        selectinload(Compose.tags),
        selectinload(Compose.parents),
        selectinload(Compose.respin_of),
        selectinload(Compose.children),
        selectinload(Compose.respun_by),
    )
    for key, data in search_query.items():
        value, suffix = data
        column = getattr(Compose, key)
        if suffix == "_contains":
            query = query.filter(column.contains(value))
        elif suffix == "_startswith":
            query = query.filter(column.startswith(value))
        elif suffix == "_endswith":
            query = query.filter(column.endswith(value))
        else:
            query = query.filter(column == value)

    date_before = flask_request.args.get("date_before")
    if date_before:
        query = query.filter(Compose.date < date_before)
    date_after = flask_request.args.get("date_after")
    if date_after:
        query = query.filter(Compose.date > date_after)

    tags = flask_request.args.getlist("tag")
    if tags:
        if "" in tags:
            # Get just composes without any Compose.tags.
            query = query.filter(~Compose.tags.any())
        else:
            for tag in tags:
                if tag.startswith("-"):
                    query = query.filter(~Compose.tags.any(Tag.name == tag[1:]))
                else:
                    query = query.filter(Compose.tags.any(Tag.name == tag))

    query = _order_by(flask_request, query, Compose, allowed_keys, ["-date", "-id"])

    page = flask_request.args.get("page", 1, type=int)
    per_page = flask_request.args.get("per_page", 10, type=int)
    return query.paginate(page=page, per_page=per_page, error_out=False)


def filter_tags(flask_request):
    """
    Returns a flask_sqlalchemy.Pagination object based on the request parameters
    :param request: Flask request object
    :return: flask_sqlalchemy.Pagination
    """
    search_query = dict()

    for key in ["id", "name"]:
        if flask_request.args.get(key, None):
            search_query[key] = flask_request.args[key]

    query = Tag.query

    if search_query:
        query = query.filter_by(**search_query)

    query = _order_by(flask_request, query, Tag, ["id", "name"], ["-id"])

    page = flask_request.args.get("page", 1, type=int)
    per_page = flask_request.args.get("per_page", 10, type=int)
    return query.paginate(page=page, per_page=per_page, error_out=False)


def has_required_group(user_groups, required_groups):
    """Check if user in any of the required groups.

    :param list user_groups: Groups of the user.
    :param list required_groups: Required groups.
    :return: True or False.
    :rtype: Boolean.
    """
    for grp in user_groups:
        if grp in required_groups:
            return True

    return False


def is_tagger(user, user_groups, tag):
    """Check if `user` has tagger permission of `tag`.

    :param cts.models.User user: User instance.
    :param list user_groups: Groups of the user.
    :param cts.models.Tag tag: Tag instance.
    :return: True or False.
    :rtype: Boolean.
    """
    if user in tag.taggers:
        return True

    if tag.tagger_groups:
        tagger_groups = [tg.group for tg in tag.tagger_groups]
        return has_required_group(user_groups, tagger_groups)

    return False


def is_untagger(user, user_groups, tag):
    """Check if `user` has untagger permission of `tag`.

    :param cts.models.User user: User instance.
    :param list user_groups: Groups of the user.
    :param cts.models.Tag tag: Tag instance.
    :return: True or False.
    :rtype: Boolean.
    """
    if user in tag.untaggers:
        return True

    if tag.untagger_groups:
        untagger_groups = [tg.group for tg in tag.untagger_groups]
        return has_required_group(user_groups, untagger_groups)

    return False
