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
from cts.models import Compose, User, Tag

from utils import ModelsBaseTest


@login_manager.user_loader
def user_loader(username):
    return User.find_user_by_name(username=username)


class ViewBaseTest(ModelsBaseTest):
    def setUp(self):
        super(ViewBaseTest, self).setUp()

        self.oidc_base_namespace = patch.object(
            conf, "oidc_base_namespace", new="http://example.com/"
        )
        self.oidc_base_namespace.start()

        patched_allowed_builders = {
            "groups": [],
            "users": ["odcs"],
        }
        patched_admins = {"groups": ["admin"], "users": ["root"]}
        self.patch_allowed_builders = patch.object(
            cts.auth.conf, "allowed_builders", new=patched_allowed_builders
        )
        self.patch_admins = patch.object(cts.auth.conf, "admins", new=patched_admins)
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
                patch_auth_backend = patch.object(
                    cts.auth.conf, "auth_backend", new="kerberos"
                )
                patch_auth_backend.start()
                if not User.find_user_by_name(user):
                    User.create_user(username=user)
                    db.session.commit()
                flask.g.user = User.find_user_by_name(user)
                flask.g.oidc_scopes = [
                    "{0}{1}".format(conf.oidc_base_namespace, "new-compose")
                ]

                if groups is not None:
                    if isinstance(groups, list):
                        flask.g.groups = groups
                    else:
                        flask.g.groups = [groups]
                else:
                    flask.g.groups = []
                with self.client.session_transaction() as sess:
                    sess["user_id"] = user
                    sess["_fresh"] = True
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
            cts.auth.conf, "auth_backend", new="openidc"
        )
        self.patch_auth_backend.start()

    def tearDown(self):
        super(TestOpenIDCLogin, self).tearDown()
        self.patch_auth_backend.stop()

    def test_openidc_post_unauthorized(self):
        rv = self.client.post("/api/1/composes/", data="")
        self.assertEqual(rv.status, "401 UNAUTHORIZED")


class TestViews(ViewBaseTest):
    maxDiff = None

    def setup_test_data(self):
        # Create two composes.
        User.create_user(username="odcs")
        self.c1 = Compose.create(db.session, "odcs", self.ci)[0]
        Compose.create(db.session, "odcs", self.ci)

    def test_about_get(self):
        rv = self.client.get("/api/1/about/")
        data = json.loads(rv.get_data(as_text=True))
        self.assertEqual(data, {"version": version, "auth_backend": "noauth"})

    def test_composes_post_invalid_json(self):
        with self.test_request_context(user="odcs"):
            rv = self.client.post("/api/1/composes/", data="{")
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(rv.status, "400 BAD REQUEST")
        self.assertEqual(data["error"], "Bad Request")
        self.assertEqual(data["status"], 400)
        self.assertTrue(data["message"].find("Failed to decode JSON object") != -1)

    def test_composes_get(self):
        self.ci.compose.date = "20200518"
        Compose.create(db.session, "odcs", self.ci)
        with self.test_request_context(user="odcs"):
            rv = self.client.get("/api/1/composes/?date=20200518")
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(len(data["items"]), 1)

    def test_composes_get_startswith(self):
        self.ci.compose.date = "20200518"
        Compose.create(db.session, "odcs", self.ci)
        with self.test_request_context(user="odcs"):
            rv = self.client.get(
                "/api/1/composes/?id_startswith=Fedora-Rawhide-20200517.n."
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(len(data["items"]), 2)

    def test_composes_get_endswith(self):
        self.ci.compose.date = "20200518"
        Compose.create(db.session, "odcs", self.ci)
        with self.test_request_context(user="odcs"):
            rv = self.client.get("/api/1/composes/?date_endswith=0517")
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(len(data["items"]), 2)

    def test_composes_get_contains(self):
        self.ci.compose.date = "20200518"
        Compose.create(db.session, "odcs", self.ci)
        with self.test_request_context(user="odcs"):
            rv = self.client.get("/api/1/composes/?id_contains=20200517.n.")
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(len(data["items"]), 2)

    def test_composes_get_untagged(self):
        self.ci.compose.date = "20200518"
        Compose.create(db.session, "odcs", self.ci)
        with self.test_request_context(user="odcs"):
            rv = self.client.get("/api/1/composes/?tag=&date=20200518")
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(len(data["items"]), 1)

    def test_composes_get_order_by(self):
        self.ci.compose.date = "20200518"
        self.ci.compose.respin = 0
        Compose.create(db.session, "odcs", self.ci)
        self.ci.compose.date = "20200519"
        self.ci.release.short = "Z"
        self.ci.compose.respin = 0
        Compose.create(db.session, "odcs", self.ci)
        with self.test_request_context(user="odcs"):
            rv = self.client.get("/api/1/composes/")
            data = json.loads(rv.get_data(as_text=True))

        compose_ids = [
            c["compose_info"]["payload"]["compose"]["id"] for c in data["items"]
        ]
        expected_compose_ids = [
            "Z-Rawhide-20200519.n.0",
            "Fedora-Rawhide-20200518.n.0",
            "Fedora-Rawhide-20200517.n.2",
            "Fedora-Rawhide-20200517.n.1",
        ]
        self.assertEqual(expected_compose_ids, compose_ids)

    def test_composes_post(self):
        with self.test_request_context(user="odcs"):
            rv = self.client.post(
                "/api/1/composes/", json={"compose_info": json.loads(self.ci.dumps())}
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(
            data["payload"]["compose"]["id"], "Fedora-Rawhide-20200517.n.3"
        )

        db.session.expire_all()
        c = (
            db.session.query(Compose)
            .filter(Compose.id == "Fedora-Rawhide-20200517.n.3")
            .one()
        )
        self.assertEqual(c.respin, 3)

    def test_composes_post_no_compose_info(self):
        with self.test_request_context(user="odcs"):
            rv = self.client.post("/api/1/composes/", json={"foo": "bar"})
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(rv.status, "400 BAD REQUEST")
        self.assertEqual(data["error"], "Bad Request")
        self.assertEqual(data["status"], 400)
        self.assertEqual(data["message"], 'No "compose_info" field in JSON POST data.')

    def test_composes_post_invalid_compose_info(self):
        with self.test_request_context(user="odcs"):
            rv = self.client.post(
                "/api/1/composes/", json={"compose_info": {"foo": "bar"}}
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(rv.status, "400 BAD REQUEST")
        self.assertEqual(data["error"], "Bad Request")
        self.assertEqual(data["status"], 400)
        self.assertTrue(data["message"].startswith('Cannot parse "compose_info"'))

    def test_composes_post_builder_not_allowed(self):
        with self.test_request_context(user="foo"):
            rv = self.client.post(
                "/api/1/composes/", json={"compose_info": json.loads(self.ci.dumps())}
            )

        self.assertEqual(rv.status, "403 FORBIDDEN")

    def test_composes_post_parent_compose_ids(self):
        with self.test_request_context(user="odcs"):
            rv = self.client.post(
                "/api/1/composes/",
                json={
                    "compose_info": json.loads(self.ci.dumps()),
                    "parent_compose_ids": [self.c1.id],
                },
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(
            data["payload"]["compose"]["id"], "Fedora-Rawhide-20200517.n.3"
        )

        db.session.expire_all()
        c = (
            db.session.query(Compose)
            .filter(Compose.id == "Fedora-Rawhide-20200517.n.3")
            .one()
        )
        c1 = (
            db.session.query(Compose)
            .filter(Compose.id == "Fedora-Rawhide-20200517.n.1")
            .one()
        )
        self.assertEqual(c.parents, [c1])
        self.assertEqual(c1.children, [c])

    def test_composes_post_wrong_parent_compose_ids(self):
        with self.test_request_context(user="odcs"):
            rv = self.client.post(
                "/api/1/composes/",
                json={
                    "compose_info": json.loads(self.ci.dumps()),
                    "parent_compose_ids": ["non-existing"],
                },
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(
            data["message"], "Cannot find parent compose with id non-existing."
        )

        db.session.expire_all()
        c = (
            db.session.query(Compose)
            .filter(Compose.id == "Fedora-Rawhide-20200517.n.3")
            .first()
        )
        self.assertEqual(c, None)

    def test_composes_post_respin_of(self):
        with self.test_request_context(user="odcs"):
            rv = self.client.post(
                "/api/1/composes/",
                json={
                    "compose_info": json.loads(self.ci.dumps()),
                    "respin_of": self.c1.id,
                },
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(
            data["payload"]["compose"]["id"], "Fedora-Rawhide-20200517.n.3"
        )

        db.session.expire_all()
        c = (
            db.session.query(Compose)
            .filter(Compose.id == "Fedora-Rawhide-20200517.n.3")
            .one()
        )
        c1 = (
            db.session.query(Compose)
            .filter(Compose.id == "Fedora-Rawhide-20200517.n.1")
            .one()
        )
        self.assertEqual(c.respin_of, c1)
        self.assertEqual(c1.respun_by, [c])

    def test_composes_post_wrong_respin_of(self):
        with self.test_request_context(user="odcs"):
            rv = self.client.post(
                "/api/1/composes/",
                json={
                    "compose_info": json.loads(self.ci.dumps()),
                    "respin_of": "non-existing",
                },
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(
            data["message"], "Cannot find respin_of compose with id non-existing."
        )

        db.session.expire_all()
        c = (
            db.session.query(Compose)
            .filter(Compose.id == "Fedora-Rawhide-20200517.n.3")
            .first()
        )
        self.assertEqual(c, None)

    def test_tags_get(self):
        self.test_tags_post()
        rv = self.client.get("/api/1/tags/")
        data = json.loads(rv.get_data(as_text=True))
        expected_data = {
            "items": [
                {
                    "description": "Periodic compose",
                    "documentation": "Foo",
                    "id": 1,
                    "name": "periodic",
                    "taggers": [],
                    "untaggers": [],
                }
            ],
            "meta": {
                "first": "http://localhost/api/1/tags/?page=1&per_page=10",
                "last": "http://localhost/api/1/tags/?page=1&per_page=10",
                "next": None,
                "page": 1,
                "pages": 1,
                "per_page": 10,
                "prev": None,
                "total": 1,
            },
        }
        self.assertEqual(data, expected_data)

    def test_tags_get_single_tag(self):
        self.test_tags_post()
        rv = self.client.get("/api/1/tags/1")
        data = json.loads(rv.get_data(as_text=True))
        expected_data = {
            "description": "Periodic compose",
            "documentation": "Foo",
            "id": 1,
            "name": "periodic",
            "taggers": [],
            "untaggers": [],
        }
        self.assertEqual(data, expected_data)

    def test_tags_get_single_name(self):
        self.test_tags_post()
        rv = self.client.get("/api/1/tags/periodic")
        data = json.loads(rv.get_data(as_text=True))
        expected_data = {
            "description": "Periodic compose",
            "documentation": "Foo",
            "id": 1,
            "name": "periodic",
            "taggers": [],
            "untaggers": [],
        }
        self.assertEqual(data, expected_data)

    def test_tags_post(self):
        with self.test_request_context(user="root"):
            req = {
                "name": "periodic",
                "description": "Periodic compose",
                "documentation": "Foo",
                "user_data": "Ticket #123",
            }
            rv = self.client.post("/api/1/tags/", json=req)
            data = json.loads(rv.get_data(as_text=True))

        expected_data = {
            "description": "Periodic compose",
            "documentation": "Foo",
            "id": 1,
            "name": "periodic",
            "taggers": [],
            "untaggers": [],
        }
        self.assertEqual(data, expected_data)

    def test_tags_post_unathorized(self):
        with self.test_request_context(user="odcs"):
            req = {
                "name": "periodic",
                "description": "Periodic compose",
                "documentation": "Foo",
            }
            rv = self.client.post("/api/1/tags/", json=req)
        self.assertEqual(rv.status, "403 FORBIDDEN")

    def test_tags_post_incomplete(self):
        for key in ["name", "description", "documentation"]:
            with self.test_request_context(user="root"):
                req = {
                    "name": "periodic",
                    "description": "Periodic compose",
                    "documentation": "Foo",
                }
                del req[key]
                rv = self.client.post("/api/1/tags/", json=req)
                data = json.loads(rv.get_data(as_text=True))

            self.assertEqual(rv.status, "400 BAD REQUEST")
            self.assertEqual(data["error"], "Bad Request")
            self.assertEqual(data["status"], 400)
            self.assertTrue("is not defined" in data["message"])

    def test_tags_patch(self):
        self.test_tags_post()
        with self.test_request_context(user="root"):
            req = {
                "name": "periodic-update",
                "description": "Periodic compose update",
                "documentation": "Foo update",
                "user_data": "Ticket #124",
            }
            rv = self.client.patch("/api/1/tags/1", json=req)
            data = json.loads(rv.get_data(as_text=True))

        expected_data = {
            "description": "Periodic compose update",
            "documentation": "Foo update",
            "id": 1,
            "name": "periodic-update",
            "taggers": [],
            "untaggers": [],
        }
        self.assertEqual(data, expected_data)

    def test_tags_patch_unauthorized(self):
        self.test_tags_post()
        with self.test_request_context(user="odcs"):
            req = {
                "name": "periodic-update",
                "description": "Periodic compose update",
                "documentation": "Foo update",
            }
            rv = self.client.patch("/api/1/tags/1", json=req)
        self.assertEqual(rv.status, "403 FORBIDDEN")

    def test_tags_patch_actions(self):
        self.test_tags_post()
        db.session.commit()

        for action in [
            "add_tagger",
            "remove_tagger",
            "add_untagger",
            "remove_untagger",
        ]:
            with self.test_request_context(user="root"):
                req = {"action": action, "username": "odcs"}
                rv = self.client.patch("/api/1/tags/1", json=req)
                data = json.loads(rv.get_data(as_text=True))

            expected_list = [] if "remove" in action else ["odcs"]
            expected_data = {
                "description": "Periodic compose",
                "documentation": "Foo",
                "id": 1,
                "name": "periodic",
                "taggers": expected_list if "untagger" not in action else [],
                "untaggers": expected_list if "untagger" in action else [],
            }
            self.assertEqual(data, expected_data)

    def test_tags_patch_actions_unknown_user(self):
        self.test_tags_post()
        with self.test_request_context(user="root"):
            req = {"action": "add_tagger", "username": "not-existing"}
            rv = self.client.patch("/api/1/tags/1", json=req)
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(rv.status, "400 BAD REQUEST")
        self.assertEqual(data["error"], "Bad Request")
        self.assertEqual(data["status"], 400)
        self.assertTrue("User does not exist" in data["message"])

    def test_tags_patch_actions_unknown_action(self):
        self.test_tags_post()
        db.session.commit()
        with self.test_request_context(user="root"):
            req = {"action": "not-existing", "username": "odcs"}
            rv = self.client.patch("/api/1/tags/1", json=req)
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(rv.status, "400 BAD REQUEST")
        self.assertEqual(data["error"], "Bad Request")
        self.assertEqual(data["status"], 400)
        self.assertTrue("Unknown action." in data["message"])


class TestViewsQueryByTag(ViewBaseTest):
    def setup_test_data(self):
        # Create a user
        User.create_user(username="odcs")
        # Create two tags
        Tag.create(
            db.session, "odcs", name="test", description="test", documentation="test"
        )
        Tag.create(
            db.session, "odcs", name="removed", description="test", documentation="test"
        )
        # Create composes with all combinations of tags
        self.ci.compose.respin = 0
        c, _ = Compose.create(db.session, "odcs", self.ci)
        self.ci.compose.respin = 1
        c, _ = Compose.create(db.session, "odcs", self.ci)
        c.tag("odcs", "test")
        c.tag("odcs", "removed")
        self.ci.compose.respin = 2
        c, _ = Compose.create(db.session, "odcs", self.ci)
        c.tag("odcs", "test")
        self.ci.compose.respin = 3
        c, _ = Compose.create(db.session, "odcs", self.ci)
        c.tag("odcs", "removed")

    def test_composes_get_without_tag(self):
        with self.test_request_context(user="odcs"):
            rv = self.client.get("/api/1/composes/?tag=-removed")
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(
            [c["compose_info"]["payload"]["compose"]["respin"] for c in data["items"]],
            [2, 0],
        )

    def test_composes_get_with_and_without_tag(self):
        with self.test_request_context(user="odcs"):
            rv = self.client.get("/api/1/composes/?tag=test&tag=-removed")
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(
            data["items"][0]["compose_info"]["payload"]["compose"]["respin"], 2
        )


class TestViewsQueryBeforeAfterDate(ViewBaseTest):
    def setup_test_data(self):
        # Create a user
        User.create_user(username="odcs")
        # Create composes with two different dates
        for date in ["20201110", "20201120"]:
            self.ci.compose.date = date
            Compose.create(db.session, "odcs", self.ci)

    def query_with_filter(self, query):
        with self.test_request_context(user="odcs"):
            rv = self.client.get("/api/1/composes/?" + query)
            return [
                c["compose_info"]["payload"]["compose"]["date"]
                for c in rv.get_json()["items"]
            ]

    def test_before_query_before_first(self):
        self.assertEqual(self.query_with_filter("date_before=20201101"), [])

    def test_before_query_on_first(self):
        self.assertEqual(self.query_with_filter("date_before=20201110"), [])

    def test_before_query_before_second(self):
        self.assertEqual(self.query_with_filter("date_before=20201115"), ["20201110"])

    def test_before_query_on_second(self):
        self.assertEqual(self.query_with_filter("date_before=20201120"), ["20201110"])

    def test_before_query_after_second(self):
        self.assertEqual(
            self.query_with_filter("date_before=20201130"), ["20201120", "20201110"]
        )

    def test_after_query_before_first(self):
        self.assertEqual(
            self.query_with_filter("date_after=20201101"), ["20201120", "20201110"]
        )

    def test_after_query_on_first(self):
        self.assertEqual(self.query_with_filter("date_after=20201110"), ["20201120"])

    def test_after_query_before_second(self):
        self.assertEqual(self.query_with_filter("date_after=20201115"), ["20201120"])

    def test_after_query_on_second(self):
        self.assertEqual(self.query_with_filter("date_after=20201120"), [])

    def test_after_query_after_second(self):
        self.assertEqual(self.query_with_filter("date_after=20201130"), [])

    def test_before_second_after_first(self):
        self.assertEqual(
            self.query_with_filter("date_before=20201119&date_after=20201111"), []
        )

    def test_before_first_after_second(self):
        self.assertEqual(
            self.query_with_filter("date_before=20201121&date_after=20201109"),
            ["20201120", "20201110"],
        )


class TestViewsComposeTagging(ViewBaseTest):
    maxDiff = None

    def setup_composes(self):
        User.create_user(username="root")
        User.create_user(username="odcs")
        t = Tag.create(
            db.session,
            "root",
            name="periodic",
            description="Periodic compose",
            documentation="http://localhost/",
        )
        t.add_tagger("root", "odcs")
        t.add_untagger("root", "odcs")
        self.c = Compose.create(db.session, "odcs", self.ci)[0]
        Compose.create(db.session, "odcs", self.ci)
        db.session.commit()

    def test_composes_patch_missing_action(self):
        with self.test_request_context(user="odcs"):
            req = {"tag": "periodic"}
            rv = self.client.patch(
                "/api/1/composes/Fedora-Rawhide-20200517.n.1", json=req
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(rv.status, "400 BAD REQUEST")
        self.assertEqual(data["error"], "Bad Request")
        self.assertEqual(data["status"], 400)
        self.assertEqual(data["message"], 'No "action" field in JSON PATCH data.')

    def test_composes_patch_missing_tag(self):
        for action in ["tag", "untag"]:
            with self.test_request_context(user="odcs"):
                req = {
                    "action": action,
                }
                rv = self.client.patch(
                    "/api/1/composes/Fedora-Rawhide-20200517.n.1", json=req
                )
                data = json.loads(rv.get_data(as_text=True))

            self.assertEqual(rv.status, "400 BAD REQUEST")
            self.assertEqual(data["error"], "Bad Request")
            self.assertEqual(data["status"], 400)
            self.assertEqual(data["message"], 'No "tag" field in JSON PATCH data.')

    def test_composes_patch_wrong_action(self):
        with self.test_request_context(user="odcs"):
            req = {"action": "not-existing", "tag": "periodic"}
            rv = self.client.patch(
                "/api/1/composes/Fedora-Rawhide-20200517.n.1", json=req
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(rv.status, "400 BAD REQUEST")
        self.assertEqual(data["error"], "Bad Request")
        self.assertEqual(data["status"], 400)
        self.assertEqual(data["message"], "Unknown action.")

    def test_composes_patch_tag(self):
        with self.test_request_context(user="odcs"):
            req = {"action": "tag", "tag": "periodic"}
            rv = self.client.patch(
                "/api/1/composes/Fedora-Rawhide-20200517.n.1", json=req
            )
            data = json.loads(rv.get_data(as_text=True))
        self.assertEqual(data["tags"], ["periodic"])

        with self.test_request_context(user="odcs"):
            rv = self.client.get("/api/1/composes/?tag=periodic")
            data = json.loads(rv.get_data(as_text=True))
        self.assertEqual(len(data["items"]), 1)

    def test_composes_patch_tag_no_tagger(self):
        with self.test_request_context(user="foo"):
            req = {"action": "tag", "tag": "periodic"}
            rv = self.client.patch(
                "/api/1/composes/Fedora-Rawhide-20200517.n.1", json=req
            )
        self.assertEqual(rv.status, "403 FORBIDDEN")

    def test_composes_patch_tag_admin(self):
        with self.test_request_context(user="root"):
            req = {"action": "tag", "tag": "periodic"}
            rv = self.client.patch(
                "/api/1/composes/Fedora-Rawhide-20200517.n.1", json=req
            )
            data = json.loads(rv.get_data(as_text=True))
        self.assertEqual(data["tags"], ["periodic"])

    def test_composes_patch_tag_wrong_tag(self):
        with self.test_request_context(user="odcs"):
            req = {"action": "tag", "tag": "not-existing"}
            rv = self.client.patch(
                "/api/1/composes/Fedora-Rawhide-20200517.n.1", json=req
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(rv.status, "400 BAD REQUEST")
        self.assertEqual(data["error"], "Bad Request")
        self.assertEqual(data["status"], 400)
        self.assertEqual(data["message"], 'Tag "not-existing" does not exist')

    def test_composes_patch_untag(self):
        self.c.tag("odcs", "periodic")
        with self.test_request_context(user="odcs"):
            req = {"action": "untag", "tag": "periodic"}
            rv = self.client.patch(
                "/api/1/composes/Fedora-Rawhide-20200517.n.1", json=req
            )
            data = json.loads(rv.get_data(as_text=True))
        self.assertEqual(data["tags"], [])

    def test_composes_patch_untag_no_untagger(self):
        self.c.tag("odcs", "periodic")
        db.session.commit()
        with self.test_request_context(user="foo"):
            req = {"action": "untag", "tag": "periodic"}
            rv = self.client.patch(
                "/api/1/composes/Fedora-Rawhide-20200517.n.1", json=req
            )
        self.assertEqual(rv.status, "403 FORBIDDEN")

    def test_composes_patch_untag_admin(self):
        self.c.tag("odcs", "periodic")
        db.session.commit()
        with self.test_request_context(user="root"):
            req = {"action": "untag", "tag": "periodic"}
            rv = self.client.patch(
                "/api/1/composes/Fedora-Rawhide-20200517.n.1", json=req
            )
            data = json.loads(rv.get_data(as_text=True))
        self.assertEqual(data["tags"], [])

    def test_composes_patch_untag_wrong_untag(self):
        self.c.tag("odcs", "periodic")
        with self.test_request_context(user="odcs"):
            req = {"action": "untag", "tag": "not-existing"}
            rv = self.client.patch(
                "/api/1/composes/Fedora-Rawhide-20200517.n.1", json=req
            )
            data = json.loads(rv.get_data(as_text=True))

        self.assertEqual(rv.status, "400 BAD REQUEST")
        self.assertEqual(data["error"], "Bad Request")
        self.assertEqual(data["status"], 400)
        self.assertEqual(data["message"], 'Tag "not-existing" does not exist')
