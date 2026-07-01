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
import time
import unittest
import flask
from concurrent.futures import ThreadPoolExecutor

from unittest.mock import patch, ANY, call, Mock

from cts import conf
from cts import app, db
import cts.messaging
from cts.messaging import _retry_with_backoff, _kafka_send_msg, _umb_send_msg, publish
from cts.models import Compose, User, Tag
from utils import ModelsBaseTest

try:
    import rhmsg
except ImportError:
    rhmsg = None

try:
    import kafka
except ImportError:
    kafka = None


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


@unittest.skipUnless(kafka, "kafka-python is required to run this test case.")
class TestKafkaSendMessageWhenComposeIsCreated(ModelsBaseTest):
    """Test send message when compose is created via Kafka backend"""

    disable_event_handlers = False

    def setUp(self):
        super(TestKafkaSendMessageWhenComposeIsCreated, self).setUp()
        cts.messaging._kafka_producer = None

    def tearDown(self):
        super(TestKafkaSendMessageWhenComposeIsCreated, self).tearDown()
        cts.messaging._kafka_producer = None

    def setup_composes(self):
        User.create_user(username="odcs")
        db.session.commit()

    @patch.object(conf, "messaging_backend", new="kafka")
    @patch.object(conf, "messaging_broker_urls", new=["localhost:9092"])
    @patch.object(conf, "messaging_kafka_username", new="test_user")
    @patch.object(conf, "messaging_kafka_password", new="test_password")
    @patch("kafka.KafkaProducer")
    def test_send_message(self, KafkaProducer):
        mock_producer = KafkaProducer.return_value
        test_executor = ThreadPoolExecutor(max_workers=1)

        with app.app_context():
            with patch("cts.messaging._executor", test_executor):
                flask.g.user = Mock(username="odcs")
                compose = Compose.create(db.session, "odcs", self.ci)[0]
                test_executor.shutdown(wait=True, cancel_futures=False)

            # Verify KafkaProducer was created with correct config
            call_args = KafkaProducer.call_args[1]
            self.assertEqual(call_args["bootstrap_servers"], ["localhost:9092"])
            self.assertEqual(call_args["sasl_plain_username"], "test_user")
            self.assertEqual(call_args["sasl_plain_password"], "test_password")

            # Verify message was sent to correct topic with correct content
            mock_producer.send.assert_called_once_with(
                "cts.compose-created",
                {
                    "event": "compose-created",
                    "compose": compose.json(),
                    "agent": "odcs",
                },
            )

            # Producer should not be closed on success (long-lived)
            mock_producer.close.assert_not_called()

    @patch.object(conf, "messaging_broker_urls", new=["localhost:9092"])
    @patch.object(conf, "messaging_kafka_username", new="test_user")
    @patch.object(conf, "messaging_kafka_password", new="test_password")
    @patch("kafka.KafkaProducer")
    def test_kafka_producer_closed_on_exception(self, KafkaProducer):
        """Test that producer is closed and recreated on failure"""
        mock_producer = KafkaProducer.return_value
        mock_producer.send.side_effect = Exception("Send failed")

        msgs = [{"event": "test", "data": "test_data"}]

        with patch("time.sleep"):
            with self.assertRaises(Exception):
                _kafka_send_msg(msgs)

        # Producer should be closed on each failed attempt and recreated
        # Default is 3 retries + 1 initial = 4 attempts
        self.assertEqual(mock_producer.close.call_count, 4)
        # After all retries exhausted, producer should be reset to None
        self.assertIsNone(cts.messaging._kafka_producer)

    @patch.object(conf, "messaging_broker_urls", new=["localhost:9092"])
    @patch.object(conf, "messaging_kafka_username", new="test_user")
    @patch.object(conf, "messaging_kafka_password", new="test_password")
    @patch("kafka.KafkaProducer")
    def test_kafka_producer_reused_across_calls(self, KafkaProducer):
        """Test that producer is created once and reused"""
        mock_producer = KafkaProducer.return_value

        _kafka_send_msg([{"event": "compose-created", "compose": {}}])
        _kafka_send_msg([{"event": "compose-tagged", "compose": {}}])

        # Producer should only be created once
        KafkaProducer.assert_called_once()
        # But send should be called twice
        self.assertEqual(mock_producer.send.call_count, 2)


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


class TestRetryAndAsyncPublish(unittest.TestCase):
    """Test retry logic and async publishing (backend-agnostic)"""

    def test_retry_with_backoff_success_on_first_attempt(self):
        """Test retry succeeds immediately if function works on first try"""
        call_count = [0]

        def successful_func():
            call_count[0] += 1
            return "success"

        result = _retry_with_backoff(successful_func)
        self.assertEqual(result, "success")
        self.assertEqual(call_count[0], 1)

    def test_retry_with_backoff_success_after_failures(self):
        """Test retry succeeds after some failures"""
        call_count = [0]

        def flaky_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("Temporary failure")
            return "success"

        with patch("time.sleep"):  # Mock sleep to speed up test
            result = _retry_with_backoff(flaky_func, max_retries=3)

        self.assertEqual(result, "success")
        self.assertEqual(call_count[0], 3)

    def test_retry_with_backoff_exhausts_retries(self):
        """Test retry raises exception after all retries exhausted"""
        call_count = [0]

        def always_fails():
            call_count[0] += 1
            raise ConnectionError("Persistent failure")

        with patch("time.sleep"):  # Mock sleep to speed up test
            with self.assertRaises(ConnectionError) as cm:
                _retry_with_backoff(always_fails, max_retries=2)

        self.assertIn("Persistent failure", str(cm.exception))
        self.assertEqual(call_count[0], 3)  # Initial attempt + 2 retries

    def test_publish_is_async(self):
        """Test that publish() returns immediately without blocking"""

        # Mock the backend to simulate slow operation
        slow_backend = Mock()

        def slow_send(msgs):
            time.sleep(0.1)  # Simulate slow message sending

        slow_backend.side_effect = slow_send
        test_executor = ThreadPoolExecutor(max_workers=1)

        with patch("cts.messaging._get_messaging_backend", return_value=slow_backend):
            with patch("cts.messaging._executor", test_executor):
                start = time.time()
                publish([{"event": "test"}])
                elapsed = time.time() - start

                # publish() should return immediately (much less than 0.1s)
                self.assertLess(elapsed, 0.05)

                # Wait for background thread to complete
                test_executor.shutdown(wait=True, cancel_futures=False)

                # Now the backend should have been called
                slow_backend.assert_called_once()

    def test_publish_error_handling_in_background_thread(self):
        """Test that errors in background thread are logged properly"""

        # Mock backend that raises an error
        failing_backend = Mock(side_effect=RuntimeError("Connection failed"))
        test_executor = ThreadPoolExecutor(max_workers=1)

        with patch(
            "cts.messaging._get_messaging_backend", return_value=failing_backend
        ):
            with patch("cts.messaging._executor", test_executor):
                with patch("cts.messaging.log") as mock_log:
                    publish([{"event": "test"}])

                    # Wait for background thread to complete
                    test_executor.shutdown(wait=True, cancel_futures=False)

                    # Error should have been logged
                    mock_log.exception.assert_called_once_with(
                        "Failed to publish messages to message broker."
                    )


@unittest.skipUnless(rhmsg, "rhmsg is required to run this test case.")
class TestRhmsgRetries(unittest.TestCase):
    """Test UMB-specific retry behavior"""

    @patch("rhmsg.activemq.producer.AMQProducer")
    @patch("proton.Message")
    def test_umb_send_msg_retries_on_transient_failure(
        self, mock_message, mock_producer
    ):
        """Test that _umb_send_msg retries on transient failures"""
        # Simulate transient failure then success
        attempt_count = [0]

        def producer_side_effect(*args, **kwargs):
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                raise ConnectionError("Transient network error")
            return mock_producer.return_value

        with patch("time.sleep"):  # Mock sleep to speed up test
            with patch(
                "rhmsg.activemq.producer.AMQProducer", side_effect=producer_side_effect
            ):
                # Should succeed on second attempt
                _umb_send_msg([{"event": "test", "data": "test"}])

        self.assertEqual(attempt_count[0], 2)


@unittest.skipUnless(kafka, "kafka-python is required to run this test case.")
class TestKafkaRetries(unittest.TestCase):
    """Test Kafka-specific retry behavior"""

    def setUp(self):
        cts.messaging._kafka_producer = None

    def tearDown(self):
        cts.messaging._kafka_producer = None

    @patch.object(conf, "messaging_broker_urls", new=["localhost:9092"])
    @patch.object(conf, "messaging_kafka_username", new="test_user")
    @patch.object(conf, "messaging_kafka_password", new="test_password")
    @patch.object(conf, "messaging_topic_prefix", new="cts.")
    def test_kafka_send_msg_retries_on_transient_failure(self):
        """Test that _kafka_send_msg retries on transient failures"""
        # Simulate send failure on first call, then success
        send_count = [0]
        mock_producer = Mock()

        def send_side_effect(*args, **kwargs):
            send_count[0] += 1
            if send_count[0] == 1:
                raise ConnectionError("Transient network error")

        mock_producer.send.side_effect = send_side_effect

        with patch("time.sleep"):
            with patch("kafka.KafkaProducer", return_value=mock_producer):
                _kafka_send_msg([{"event": "test", "data": "test"}])

        # First send fails, producer is closed and reset, second send succeeds
        self.assertEqual(send_count[0], 2)
