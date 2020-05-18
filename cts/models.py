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

""" SQLAlchemy Database models for the Flask app
"""


import json
from flask_login import UserMixin
from productmd import ComposeInfo

from cts import db
from cts.events import cache_composes_if_state_changed
from cts.events import start_to_publish_messages

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import FlushError
from flask_sqlalchemy import SignallingSession

event.listen(SignallingSession, 'after_flush',
             cache_composes_if_state_changed)

event.listen(SignallingSession, 'after_commit',
             start_to_publish_messages)


def commit_on_success(func):
    def _decorator(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.commit()
    return _decorator


class CTSBase(db.Model):
    __abstract__ = True


class User(CTSBase, UserMixin):
    """User information table"""

    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(200), nullable=False, unique=True)

    @classmethod
    def find_user_by_name(cls, username):
        """Find a user by username

        :param str username: a string of username to find user
        :return: user object if found, otherwise None is returned.
        :rtype: User
        """
        try:
            return db.session.query(cls).filter(cls.username == username)[0]
        except IndexError:
            return None

    @classmethod
    def create_user(cls, username):
        user = cls(username=username)
        db.session.add(user)
        return user


tags_to_composes = db.Table(
    "tags_to_composes",
    db.Column("compose_id", db.Integer, db.ForeignKey("composes.id"), nullable=False),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), nullable=False),
    db.UniqueConstraint("compose_id", "tag_id", name="unique_tags"),
)


taggers = db.Table(
    "taggers",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), nullable=False),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), nullable=False),
    db.UniqueConstraint("user_id", "tag_id", name="unique_taggers"),
)


untaggers = db.Table(
    "untaggers",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), nullable=False),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), nullable=False),
    db.UniqueConstraint("user_id", "tag_id", name="unique_untaggers"),
)


class Tag(CTSBase):
    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False, unique=True)
    # Short description of the tag.
    description = db.Column(db.String, nullable=False)
    # Link to tag documentation.
    documentation = db.Column(db.String, nullable=False)
    # Users allowed to tag the compose with this tag.
    taggers = db.relationship("User", secondary=taggers)
    # Users allowed to untag the compose with this tag.
    untaggers = db.relationship("User", secondary=untaggers)

    @classmethod
    def create(cls, session, **kwargs):
        tag = cls(**kwargs)
        session.add(tag)
        return tag

    @classmethod
    def get_by_name(cls, tag_name):
        """Find a Tag by its name

        :param str tag_name: Tag name.
        :return Tag: Tag object.
        """
        try:
            return db.session.query(cls).filter(cls.name == tag_name)[0]
        except IndexError:
            return None

    def add_tagger(self, username):
        """
        Grant `username` permissions to tag the compose with this tag.

        :param str username: Username
        :return bool: True if permissions granted, False if user does not exist.
        """
        u = User.find_user_by_name(username)
        if not u:
            return False

        self.taggers.append(u)
        return True

    def remove_tagger(self, username):
        """
        Revoke `username` permissions to tag the compose with this tag.

        :param str username: Username
        :return bool: True if permissions revoked, False if user does not exist.
        """
        u = User.find_user_by_name(username)
        if not u:
            return False

        try:
            self.taggers.remove(u)
        except ValueError:
            # User is not there, so return True.
            return True
        return True

    def add_untagger(self, username):
        """
        Grant `username` permissions to untag the compose with this tag.

        :param str username: Username
        :return bool: True if permissions granted, False if user does not exist.
        """
        u = User.find_user_by_name(username)
        if not u:
            return False

        self.untaggers.append(u)
        return True

    def remove_untagger(self, username):
        """
        Revoke `username` permissions to untag the compose with this tag.

        :param str username: Username
        :return bool: True if permissions revoked, False if user does not exist.
        """
        u = User.find_user_by_name(username)
        if not u:
            return False

        try:
            self.untaggers.remove(u)
        except ValueError:
            # User is not there, so return True.
            return True
        return True

    def json(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "documentation": self.documentation,
            "taggers": [u.username for u in self.taggers],
            "untaggers": [u.username for u in self.untaggers],
        }


class Compose(CTSBase):
    __tablename__ = "composes"

    # productmd.ComposeInfo.Compose fields
    id = db.Column(db.String, primary_key=True)
    date = db.Column(db.String)
    respin = db.Column(db.Integer)
    type = db.Column(db.String)
    label = db.Column(db.String, nullable=True)
    final = db.Column(db.Boolean, default=False)

    # productmd.ComposeInfo.Release fields
    release_name = db.Column(db.String)
    release_version = db.Column(db.String)
    release_short = db.Column(db.String)
    release_is_layered = db.Column(db.Boolean, default=False)
    release_type = db.Column(db.String, nullable=True)
    release_internal = db.Column(db.Boolean, default=False)

    # productmd.ComposeInfo.BaseProduct
    base_product_name = db.Column(db.String, nullable=True)
    base_product_short = db.Column(db.String, nullable=True)
    base_product_version = db.Column(db.String, nullable=True)
    base_product_type = db.Column(db.String, nullable=True)

    # Name of the user account which built the compose.
    builder = db.Column(db.String)
    # Compose tags.
    tags = db.relationship("Tag", secondary=tags_to_composes)

    @classmethod
    def create(cls, session, builder, ci):
        """
        Creates new Compose and commits it to database ensuring that its ID is unique.

        :param session: SQLAlchemy session.
        :param str builder: Name of the user (service) building this compose.
        :param productmd.ComposeInfo ci: ComposeInfo metadata.
        :return tuple: (Compose, productmd.ComposeInfo) - tuple with newly created
            Compose and changed ComposeInfo metadata.
        """
        while True:
            kwargs = {
                "id": ci.create_compose_id(),
                "date": ci.compose.date,
                "respin": ci.compose.respin,
                "type": ci.compose.type,
                "label": ci.compose.label,
                "final": ci.compose.final,
                "release_name": ci.release.name,
                "release_version": ci.release.version,
                "release_short": ci.release.short,
                "release_is_layered": ci.release.is_layered,
                "release_type": ci.release.type,
                "release_internal": ci.release.internal,
                "base_product_name": ci.base_product.name,
                "base_product_short": ci.base_product.short,
                "base_product_version": ci.base_product.version,
                "base_product_type": ci.base_product.type,
                "builder": builder,
            }
            compose = cls(**kwargs)
            session.add(compose)
            try:
                session.commit()
                break
            except (IntegrityError, FlushError):
                # Both IntegrityError and FlushError can be raised when the compose with
                # the same ID already exists in database.
                session.rollback()

                # Really check that the IntegrityError was caused by
                # existing compose.
                existing_compose = Compose.query.filter(
                    Compose.id == kwargs["id"]).first()
                if not existing_compose:
                    raise
            # In case session.commit() failed with IntegrityErroir, increase
            # the `respin` and try again.
            ci.compose.respin += 1
            ci.compose.id = ci.create_compose_id()

        return compose, ci

    def json(self, full=False):
        ci = ComposeInfo()
        ci.compose.id = self.id
        ci.compose.type = self.type
        ci.compose.date = self.date
        ci.compose.respin = self.respin
        ci.release.name = self.release_name
        ci.release.short = self.release_short
        ci.release.version = self.release_version
        ci.release.is_layered = self.release_is_layered
        ci.release.type = self.release_type
        ci.release.internal = self.release_internal
        ci.base_product.name = self.base_product_name
        ci.base_product.short = self.base_product_short
        ci.base_product.version = self.base_product_version
        ci.base_product.type = self.base_product_type

        return {
            "compose_info": json.loads(ci.dumps()),
            "builder": self.builder
        }

    def tag(self, tag_name):
        """
        Tag the compose with tag `tag_name.

        :param str tag_name: Name of the tag.
        :return bool: True if compose tagged, False if tag does not exist.
        """
        t = Tag.get_by_name(tag_name)
        if not t:
            return False

        self.tags.append(t)
        return True

    def untag(self, tag_name):
        """
        Remove the tag `tag_name from the compose.

        :param str tag_name: Name of the tag.
        :return bool: True if compose untagged, False if tag does not exist.
        """
        t = Tag.get_by_name(tag_name)
        if not t:
            return False

        try:
            self.tags.remove(t)
        except ValueError:
            # Tag is not there, so return True.
            return True
        return True
