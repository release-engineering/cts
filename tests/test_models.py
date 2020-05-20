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

from mock import ANY

from cts import db
from cts.models import User, Compose, Tag

from utils import ModelsBaseTest


class TestComposeModel(ModelsBaseTest):

    def test_create(self):
        User.create_user(username="odcs")
        self.ci.release.is_layered = True
        self.ci.base_product.name = "base-product"
        self.ci.base_product.short = "bp"
        self.ci.base_product.version = "Rawhide"
        self.ci.base_product.type = "ga"
        Compose.create(db.session, "odcs", self.ci)
        db.session.expire_all()

        composes = db.session.query(Compose).all()
        self.assertEqual(len(composes), 1)

        c = composes[0]
        expected_json = {
            "builder": "odcs",
            "tags": [],
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
        self.assertEqual(c.json(), expected_json)

    def test_create_respin(self):
        # Create for first time
        User.create_user(username="odcs")
        Compose.create(db.session, "odcs", self.ci)
        db.session.expire_all()

        # Create for second time and check that respin incremented.
        compose, ci = Compose.create(db.session, "odcs", self.ci)
        db.session.expire_all()

        composes = db.session.query(Compose).all()
        self.assertEqual(len(composes), 2)

        self.assertEqual(compose.respin, 2)
        self.assertEqual(ci.compose.respin, 2)


class TestTagModel(ModelsBaseTest):

    def setup_composes(self):
        User.create_user(username="odcs")
        self.compose = Compose.create(db.session, "odcs", self.ci)[0]
        self.admin = User.create_user("admin")
        self.me = User.create_user("me")
        self.you = User.create_user("you")
        t = Tag.create(
            db.session, "admin", name="periodic", description="Periodic compose",
            documentation="http://localhost/"
        )
        t.add_tagger("admin", "me")
        t.add_tagger("admin", "you")
        t.add_untagger("admin", "me")
        t = Tag.create(
            db.session, "admin", name="nightly", description="Nightly compose",
            documentation="http://localhost/"
        )
        t.add_tagger("admin", "me")
        db.session.commit()

    def test_add_remove_tagger(self):
        t = Tag.get_by_name("periodic")
        self.assertEqual(t.taggers, [self.me, self.you])

        # Remove "me".
        r = t.remove_tagger("admin", "me", "Ticket #123")
        self.assertEqual(r, True)
        self.assertEqual(t.taggers, [self.you])

        # Remove "me" again to test it does not break.
        r = t.remove_tagger("admin", "me")
        self.assertEqual(r, True)
        self.assertEqual(t.taggers, [self.you])

        # Remove "me" again to test it does not break.
        r = t.remove_tagger("admin", "me")
        self.assertEqual(r, True)
        self.assertEqual(t.taggers, [self.you])

        # Add non-existing.
        r = t.add_tagger("admin", "non-existing")
        self.assertEqual(r, False)
        self.assertEqual(t.taggers, [self.you])

        expected_tag_changes = [
            {
                'action': 'created',
                'message': None,
                'user': 'admin',
                'user_data': None,
                'time': ANY,
            },
            {
                'action': 'add_tagger',
                'message': 'Tagger permission granted to user "me".',
                'user': 'admin',
                'user_data': None,
                'time': ANY,
            },
            {
                'action': 'add_tagger',
                'message': 'Tagger permission granted to user "you".',
                'user': 'admin',
                'user_data': None,
                'time': ANY,
            },
            {
                'action': 'add_untagger',
                'message': 'Untagger permission granted to user "me".',
                'user': 'admin',
                'user_data': None,
                'time': ANY,
            },
            {
                'action': 'remove_tagger',
                'message': 'Tagger permission removed from user "me".',
                'user': 'admin',
                'user_data': 'Ticket #123',
                'time': ANY,
            },
        ]
        tag_changes = [change.json() for change in t.changes()]
        self.assertEqual(tag_changes, expected_tag_changes)

    def test_add_remove_untagger(self):
        t = Tag.get_by_name("periodic")

        # Add "me"
        r = t.add_untagger("admin", "you")
        self.assertEqual(r, True)
        self.assertEqual(t.untaggers, [self.me, self.you])

        # Remove "me".
        r = t.remove_untagger("admin", "me")
        self.assertEqual(r, True)
        self.assertEqual(t.untaggers, [self.you])

        # Remove "me" again to test it does not break.
        r = t.remove_untagger("admin", "me")
        self.assertEqual(r, True)
        self.assertEqual(t.untaggers, [self.you])

        # Remove "me" again to test it does not break.
        r = t.remove_untagger("admin", "me")
        self.assertEqual(r, True)
        self.assertEqual(t.untaggers, [self.you])

        # Add non-existing.
        r = t.add_untagger("admin", "non-existing")
        self.assertEqual(r, False)
        self.assertEqual(t.untaggers, [self.you])

    def test_json(self):
        expected_json = {
            "description": "Periodic compose",
            "documentation": "http://localhost/",
            "id": 1,
            "name": "periodic",
            "taggers": ["me", "you"],
            "untaggers": ["me"]
        }
        self.assertEqual(Tag.get_by_name("periodic").json(), expected_json)

    def test_compose_tagging(self):
        self.assertEqual(self.compose.tags, [])

        # Tag with "periodic"
        ret = self.compose.tag("odcs", "periodic", user_data="Ticket #123")
        db.session.commit()
        db.session.expire_all()
        self.compose = db.session.query(Compose).first()
        self.assertEqual(self.compose.tags, [Tag.get_by_name("periodic")])
        self.assertEqual(ret, True)

        # Untag "nightly" which is not tagged yet.
        ret = self.compose.untag("odcs", "nightly")
        self.assertEqual(ret, True)
        self.assertEqual(self.compose.tags, [Tag.get_by_name("periodic")])

        # Untag "periodic"
        ret = self.compose.untag("odcs", "periodic")
        self.assertEqual(ret, True)
        self.assertEqual(self.compose.tags, [])

        # Tag with "non-existing"
        ret = self.compose.tag("odcs", "non-existing")
        self.assertEqual(ret, False)
        self.assertEqual(self.compose.tags, [])

        expected_compose_changes = [
            {
                'action': 'created',
                'message': None,
                'time': ANY,
                'user': 'odcs',
                'user_data': None
            },
            {
                'action': 'tagged',
                'message': 'User "odcs" added "periodic" tag.',
                'time': ANY,
                'user': 'odcs',
                'user_data': "Ticket #123"
            },
            {
                'action': 'untagged',
                'message': 'User "odcs" removed "periodic" tag.',
                'time': ANY,
                'user': 'odcs',
                'user_data': None
            }
        ]
        compose_changes = [change.json() for change in self.compose.changes()]
        self.assertEqual(compose_changes, expected_compose_changes)


class TestUserModel(ModelsBaseTest):

    def test_find_by_email(self):
        db.session.add(User(username='tester1'))
        db.session.add(User(username='admin'))
        db.session.commit()

        user = User.find_user_by_name('admin')
        self.assertEqual('admin', user.username)

    def test_create_user(self):
        User.create_user(username='tester2')
        db.session.commit()

        user = User.find_user_by_name('tester2')
        self.assertEqual('tester2', user.username)

    def test_no_group_is_added_if_no_groups(self):
        User.create_user(username='tester1')
        db.session.commit()

        user = User.find_user_by_name('tester1')
        self.assertEqual('tester1', user.username)
