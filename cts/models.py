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


from flask_login import UserMixin

from cts import db
from cts.events import cache_composes_if_state_changed
from cts.events import start_to_publish_messages

from sqlalchemy import event
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


class Compose(CTSBase):
    __tablename__ = "composes"
    id = db.Column(db.String, primary_key=True)

    @classmethod
    def create(cls, session, **kwargs):
        compose = cls(**kwargs)
        session.add(compose)
        return compose

    def json(self, full=False):
        return {
            'id': self.id,
        }
