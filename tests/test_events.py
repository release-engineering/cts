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

from mock import patch

from cts import conf
from cts import db
from cts.models import Compose
from utils import ModelsBaseTest

try:
    import rhmsg
except ImportError:
    rhmsg = None

try:
    import fedora_messaging
except ImportError:
    fedora_messaging = None


@unittest.skipUnless(rhmsg, 'rhmsg is required to run this test case.')
class TestRHMsgSendMessageWhenComposeIsCreated(ModelsBaseTest):
    """Test send message when compose is created"""

    disable_event_handlers = False

    def setUp(self):
        super(TestRHMsgSendMessageWhenComposeIsCreated, self).setUp()

        # Real lock is not required for running tests
        self.mock_lock = patch('threading.Lock')
        self.mock_lock.start()

    def tearDown(self):
        super(TestRHMsgSendMessageWhenComposeIsCreated, self).tearDown()
        self.mock_lock.stop()

    def setup_composes(self):
        self.compose = Compose.create(db.session, "odcs", self.ci)[0]
        db.session.commit()

    @patch.object(conf, 'messaging_backend', new='rhmsg')
    @patch('rhmsg.activemq.producer.AMQProducer')
    @patch('proton.Message')
    def test_send_message(self, Message, AMQProducer):
        compose = Compose.create(db.session, "odcs", self.ci)[0]

        self.assertEqual(
            json.dumps({'event': 'state-changed', 'compose': compose.json()}),
            Message.return_value.body)

        producer_send = AMQProducer.return_value.__enter__.return_value.send
        producer_send.assert_called_once_with(Message.return_value)


@unittest.skipUnless(fedora_messaging, 'fedora_messaging is required to run this test case.')
class TestFedoraMessagingSendMessageWhenComposeIsCreated(ModelsBaseTest):
    """Test send message when compose is created"""

    disable_event_handlers = False

    def setUp(self):
        super(TestFedoraMessagingSendMessageWhenComposeIsCreated, self).setUp()

        # Real lock is not required for running tests
        self.mock_lock = patch('threading.Lock')
        self.mock_lock.start()

    def tearDown(self):
        super(TestFedoraMessagingSendMessageWhenComposeIsCreated, self).tearDown()
        self.mock_lock.stop()

    def setup_composes(self):
        self.compose = Compose.create(db.session, "odcs", self.ci)[0]

    @patch.object(conf, 'messaging_backend', new='fedora-messaging')
    @patch('fedora_messaging.api.Message')
    @patch('fedora_messaging.api.publish')
    def test_send_message(self, publish, Message):
        compose = Compose.create(db.session, "odcs", self.ci)[0]

        Message.assert_called_once_with(
            topic="cts.compose.state-changed",
            body={'event': 'state-changed', 'compose': compose.json()})

        publish.assert_called_once_with(Message.return_value)
