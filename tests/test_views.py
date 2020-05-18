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

import contextlib
import json


import flask

from mock import patch

import cts.auth
from cts import conf, db, app, login_manager, version
from cts.models import Compose, User

from utils import ModelsBaseTest


@login_manager.user_loader
def user_loader(username):
    return User.find_user_by_name(username=username)


class ViewBaseTest(ModelsBaseTest):

    def setUp(self):
        super(ViewBaseTest, self).setUp()

        self.oidc_base_namespace = patch.object(conf, 'oidc_base_namespace',
                                                new='http://example.com/')
        self.oidc_base_namespace.start()

        patched_allowed_builders = {
            'groups': [],
            'users': ['odcs'],
        }
        patched_admins = {'groups': ['admin'], 'users': ['root']}
        self.patch_allowed_builders = patch.object(
            cts.auth.conf, 'allowed_builders', new=patched_allowed_builders
        )
        self.patch_admins = patch.object(cts.auth.conf,
                                         'admins',
                                         new=patched_admins)
        self.patch_allowed_builders.start()
        self.patch_admins.start()

        self.client = app.test_client()

        self.setup_test_data()

    def tearDown(self):
        super(ViewBaseTest, self).tearDown()

        self.oidc_base_namespace.stop()
        self.patch_allowed_builders.stop()
        self.patch_admins.stop()

    @contextlib.contextmanager
    def test_request_context(self, user=None, groups=None, **kwargs):
        with app.test_request_context(**kwargs):
            patch_auth_backend = None
            if user is not None:
                # authentication is disabled with auth_backend=noauth
                patch_auth_backend = patch.object(cts.auth.conf,
                                                  'auth_backend',
                                                  new='kerberos')
                patch_auth_backend.start()
                if not User.find_user_by_name(user):
                    User.create_user(username=user)
                    db.session.commit()
                flask.g.user = User.find_user_by_name(user)
                flask.g.oidc_scopes = [
                    '{0}{1}'.format(conf.oidc_base_namespace, 'new-compose')
                ]

                if groups is not None:
                    if isinstance(groups, list):
                        flask.g.groups = groups
                    else:
                        flask.g.groups = [groups]
                else:
                    flask.g.groups = []
                with self.client.session_transaction() as sess:
                    sess['user_id'] = user
                    sess['_fresh'] = True
            try:
                yield
            finally:
                if patch_auth_backend is not None:
                    patch_auth_backend.stop()

    def setup_test_data(self):
        """Set up data for running tests"""


class TestOpenIDCLogin(ViewBaseTest):
    """Test that OpenIDC login"""

    def setUp(self):
        super(TestOpenIDCLogin, self).setUp()
        self.patch_auth_backend = patch.object(
            cts.auth.conf, 'auth_backend', new='openidc')
        self.patch_auth_backend.start()

    def tearDown(self):
        super(TestOpenIDCLogin, self).tearDown()
        self.patch_auth_backend.stop()

    def test_openidc_post_unauthorized(self):
        rv = self.client.post('/api/1/composes/', data="")
        self.assertEqual(rv.status, '401 UNAUTHORIZED')


class TestViews(ViewBaseTest):
    maxDiff = None

    def setup_test_data(self):
        # Create two composes.
        Compose.create(db.session, "odcs", self.ci)
        Compose.create(db.session, "odcs", self.ci)

    def test_about_get(self):
        rv = self.client.get('/api/1/about/')
        data = json.loads(rv.get_data(as_text=True))
        self.assertEqual(data, {'version': version, 'auth_backend': 'noauth'})

    def test_composes_post_invalid_json(self):
        with self.test_request_context(user='odcs'):
            rv = self.client.post('/api/1/composes/', data="{")
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(rv.status, '400 BAD REQUEST')
        self.assertEqual(data["error"], "Bad Request")
        self.assertEqual(data["status"], 400)
        self.assertTrue(data["message"].find("Failed to decode JSON object") != -1)

    def test_composes_post(self):
        with self.test_request_context(user='odcs'):
            rv = self.client.post(
                '/api/1/composes/',
                json={"compose_info": json.loads(self.ci.dumps())}
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(data["payload"]["compose"]["id"], "Fedora-Rawhide-20200517.n.3")

        db.session.expire_all()
        c = db.session.query(Compose).filter(Compose.id == "Fedora-Rawhide-20200517.n.3").one()
        self.assertEqual(c.respin, 3)

    def test_composes_post_no_compose_info(self):
        with self.test_request_context(user='odcs'):
            rv = self.client.post(
                '/api/1/composes/',
                json={"foo": "bar"}
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(rv.status, '400 BAD REQUEST')
        self.assertEqual(data["error"], "Bad Request")
        self.assertEqual(data["status"], 400)
        self.assertEqual(data["message"], 'No "compose_info" field in JSON POST data.')

    def test_composes_post_invalid_compose_info(self):
        with self.test_request_context(user='odcs'):
            rv = self.client.post(
                '/api/1/composes/',
                json={"compose_info": {"foo": "bar"}}
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(rv.status, '400 BAD REQUEST')
        self.assertEqual(data["error"], "Bad Request")
        self.assertEqual(data["status"], 400)
        self.assertTrue(data["message"].startswith('Cannot parse "compose_info"'))

    def test_composes_post_builder_not_allowed(self):
        with self.test_request_context(user='foo'):
            rv = self.client.post(
                '/api/1/composes/',
                json={"compose_info": json.loads(self.ci.dumps())}
            )

        self.assertEqual(rv.status, '403 FORBIDDEN')
