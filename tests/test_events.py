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
#
# Written by Chenxiong Qi <cqi@redhat.com>

import json
import unittest
import flask

from unittest.mock import patch, ANY, call, Mock

from cts import conf
from cts import app, db
from cts.models import Compose, User, Tag
from utils import ModelsBaseTest

try:
    import rhmsg
except ImportError:
    rhmsg = None


@unittest.skipUnless(rhmsg, "rhmsg is required to run this test case.")
class TestRHMsgSendMessageWhenComposeIsCreated(ModelsBaseTest):
    """Test send message when compose is created"""

    disable_event_handlers = False

    def setUp(self):
        super(TestRHMsgSendMessageWhenComposeIsCreated, self).setUp()

        # Real lock is not required for running tests
        self.mock_lock = patch("threading.Lock")
        self.mock_lock.start()

    def tearDown(self):
        super(TestRHMsgSendMessageWhenComposeIsCreated, self).tearDown()
        self.mock_lock.stop()

    def setup_composes(self):
        User.create_user(username="odcs")
        db.session.commit()

    @patch.object(conf, "messaging_backend", new="rhmsg")
    @patch("rhmsg.activemq.producer.AMQProducer")
    @patch("proton.Message")
    def test_send_message(self, Message, AMQProducer):
        with app.app_context():
            flask.g.user = Mock(username="odcs")
            compose = Compose.create(db.session, "odcs", self.ci)[0]

            self.assertEqual(
                json.dumps(
                    {
                        "event": "compose-created",
                        "compose": compose.json(),
                        "agent": "odcs",
                    }
                ),
                Message.return_value.body,
            )

            producer_send = AMQProducer.return_value.__enter__.return_value.send
            producer_send.assert_called_once_with(Message.return_value)


@patch("cts.messaging.publish")
class TestMessaging(ModelsBaseTest):
    """Test send message when compose is created"""

    disable_event_handlers = False

    def setUp(self):
        super(TestMessaging, self).setUp()

        # Real lock is not required for running tests
        self.mock_lock = patch("threading.Lock")
        self.mock_lock.start()

    def tearDown(self):
        super(TestMessaging, self).tearDown()
        self.mock_lock.stop()

    def setup_composes(self):
        User.create_user(username="odcs")
        self.compose = Compose.create(db.session, "odcs", self.ci)[0]
        self.me = User.create_user("me")
        Tag.create(
            db.session,
            "me",
            name="periodic",
            description="Periodic compose",
            documentation="http://localhost/",
        )
        Tag.create(
            db.session,
            "me",
            name="nightly",
            description="Nightly compose",
            documentation="http://localhost/",
        )
        Tag.create(
            db.session,
            "me",
            name="nightly-requested",
            description="Nightly-requested compose",
            documentation="http://localhost/",
        )
        Tag.create(
            db.session,
            "me",
            name="candidate-requested",
            description="Candidate-requested compose",
            documentation="http://localhost/",
        )
        Tag.create(
            db.session,
            "me",
            name="development-nightly-requested",
            description="Development nightly requsted compose",
            documentation="http://localhost/",
        )

    def test_message_compose_create(self, publish):
        with app.app_context():
            flask.g.user = Mock(username="odcs")
            self.ci.compose.respin += 1
            compose = Compose.create(db.session, "odcs", self.ci)[0]
            db.session.commit()

            publish.assert_called_once_with(
                [
                    {
                        "event": "compose-created",
                        "agent": "odcs",
                        "compose": compose.json(),
                    }
                ]
            )

    def test_message_compose_tag(self, publish):
        with app.app_context():
            flask.g.user = Mock(username="odcs")
            self.compose.tag("odcs", "periodic")
            db.session.commit()
            self.compose.tag("odcs", "nightly", "add nightly tag")
            db.session.commit()

        expected_call = call(
            [
                {
                    "event": "compose-tagged",
                    "tag": "periodic",
                    "compose": ANY,
                    "agent": "odcs",
                    "user_data": None,
                }
            ]
        )
        self.assertEqual(publish.mock_calls[0], expected_call)

        expected_call = call(
            [
                {
                    "event": "compose-tagged",
                    "tag": "nightly",
                    "compose": ANY,
                    "agent": "odcs",
                    "user_data": "add nightly tag",
                }
            ]
        )
        self.assertEqual(publish.mock_calls[1], expected_call)

    def test_message_compose_untag(self, publish):
        with app.app_context():
            flask.g.user = Mock(username="odcs")
            self.compose.tag("odcs", "periodic")
            db.session.commit()
            self.compose.tag("odcs", "nightly")
            db.session.commit()

            self.compose.untag("odcs", "periodic")
            db.session.commit()
            self.compose.untag("odcs", "nightly", "untag nightly")
            db.session.commit()

        expected_call = call(
            [
                {
                    "event": "compose-untagged",
                    "tag": "periodic",
                    "compose": ANY,
                    "agent": "odcs",
                    "user_data": None,
                }
            ]
        )
        self.assertEqual(publish.mock_calls[2], expected_call)

        expected_call = call(
            [
                {
                    "event": "compose-untagged",
                    "tag": "nightly",
                    "compose": ANY,
                    "agent": "odcs",
                    "user_data": "untag nightly",
                }
            ]
        )
        self.assertEqual(publish.mock_calls[3], expected_call)

    def test_retag_stale_composes(self, publish):
        import datetime
        from freezegun import freeze_time

        freezer = freeze_time("2021-01-01 00:00:00")
        with app.app_context():
            flask.g.user = Mock(username="odcs")
            freezer.start()
            self.compose.tag("odcs", "nightly-requested")
            db.session.commit()
            self.compose.tag("odcs", "candidate-requested")
            db.session.commit()
            self.compose.tag("odcs", "nightly")
            db.session.commit()
            freezer.stop()

            # Retag only the -requested tags when 1 hour timeout occurs
            timeout = datetime.timedelta(hours=1)
            self.compose.tag("odcs", "development-nightly-requested")
            db.session.commit()
            retags = [x for x in self.compose.retag_stale_composes("odcs", timeout)]

        # There should be 3 retagging check for all requested tag, nightly-requested, candidate-requested, development-nightly-requested
        self.assertEqual(len(retags), 3)

        expected_call = call(
            [
                {
                    "event": "compose-untagged",
                    "tag": "nightly-requested",
                    "compose": ANY,
                    "user_data": None,
                    "agent": "odcs",
                }
            ]
        )
        self.assertEqual(publish.mock_calls[4], expected_call)

        expected_call = call(
            [
                {
                    "event": "compose-tagged",
                    "tag": "nightly-requested",
                    "compose": ANY,
                    "user_data": None,
                    "agent": "odcs",
                }
            ]
        )
        self.assertEqual(publish.mock_calls[5], expected_call)

        expected_call = call(
            [
                {
                    "event": "compose-untagged",
                    "tag": "candidate-requested",
                    "compose": ANY,
                    "user_data": None,
                    "agent": "odcs",
                }
            ]
        )
        self.assertEqual(publish.mock_calls[6], expected_call)

        expected_call = call(
            [
                {
                    "event": "compose-tagged",
                    "tag": "candidate-requested",
                    "compose": ANY,
                    "user_data": None,
                    "agent": "odcs",
                }
            ]
        )
        self.assertEqual(publish.mock_calls[7], expected_call)
        # There should be 8 mock calls, since timeout is not occured for development-nightly-requested compose and nightly compose is not retagged
        self.assertEqual(len(publish.mock_calls), 8)
