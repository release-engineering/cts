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
# Written by Chenxiong Qi <cqi@redhat.com>

import atexit
import json
import time
from concurrent.futures import ThreadPoolExecutor
from logging import getLogger

from flask import current_app

log = getLogger(__name__)

__all__ = ("publish",)

# Thread pool for async message publishing (single worker to serialize message sending)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cts-messaging")


def _snapshot_messaging_config(config):
    """Capture all MESSAGING_* keys into a plain dict for background threads."""
    return {k: v for k, v in config.items() if k.startswith("MESSAGING_")}


def publish(msgs, config=None):
    """
    Publish messages to message broker asynchronously.

    Messages are published in a background thread to avoid blocking HTTP requests.
    Failures are logged but do not prevent the HTTP response from being sent.
    """
    if config is None:
        config = current_app.config
    msg_conf = _snapshot_messaging_config(config)
    backend = _get_messaging_backend(msg_conf)
    if backend is not None:

        def _send():
            try:
                backend(msgs, msg_conf)
            except Exception:
                log.exception("Failed to publish messages to message broker.")

        _executor.submit(_send)


def _retry_with_backoff(func, max_retries=3, initial_delay=1.0, backoff_multiplier=2.0):
    """
    Retry a function with exponential backoff.

    Args:
        func: Callable to retry
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        backoff_multiplier: Multiplier for exponential backoff (default: 2.0)

    Returns:
        Result of the function call

    Raises:
        The last exception if all retries fail
    """
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                log.warning(
                    f"Messaging attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay *= backoff_multiplier
            else:
                log.error(f"Messaging failed after {max_retries + 1} attempts: {e}")

    raise last_exception


_kafka_producer = None


def _normalize_kafka_compression(compression):
    """Return a compression_type value accepted by kafka-python."""
    # kafka-python uses Python None to mean "no compression"; the string
    # "none" (which may come from a config file) is not accepted.
    if compression and compression.lower() == "none":
        return None
    return compression


def _close_kafka_producer(flush=False):
    """Close the module-level Kafka producer, if any."""
    global _kafka_producer
    if _kafka_producer is None:
        return
    try:
        if flush:
            _kafka_producer.flush()
        _kafka_producer.close()
    except Exception:
        pass
    _kafka_producer = None


def _shutdown_messaging():
    """Drain pending publishes, then close the long-lived Kafka producer."""
    _executor.shutdown(wait=True, cancel_futures=False)
    _close_kafka_producer(flush=True)


def _get_kafka_producer(msg_conf):
    """Get or create a long-lived Kafka producer.

    The producer is created lazily on first use and reused for subsequent
    calls to avoid repeated TCP/TLS/SASL handshakes.
    """
    global _kafka_producer
    if _kafka_producer is None:
        from kafka import KafkaProducer

        _kafka_producer = KafkaProducer(
            bootstrap_servers=msg_conf.get("MESSAGING_BROKER_URLS", []),
            compression_type=_normalize_kafka_compression(
                msg_conf.get("MESSAGING_KAFKA_COMPRESSION_TYPE", "snappy")
            ),
            security_protocol=msg_conf.get(
                "MESSAGING_KAFKA_SECURITY_PROTOCOL", "SASL_SSL"
            ),
            sasl_mechanism=msg_conf.get(
                "MESSAGING_KAFKA_SASL_MECHANISM", "SCRAM-SHA-512"
            ),
            sasl_plain_username=msg_conf.get("MESSAGING_KAFKA_USERNAME", ""),
            sasl_plain_password=msg_conf.get("MESSAGING_KAFKA_PASSWORD", ""),
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
    return _kafka_producer


atexit.register(_shutdown_messaging)


def _kafka_send_msg(msgs, msg_conf):
    """Send messages to Kafka.

    Uses a persistent producer that is reused across calls. Retries are handled
    by kafka-python; flush() waits for delivery (or final failure) so errors can
    be logged by the caller.

    :param list[dict] msgs: List of messages to be sent.
    :param dict msg_conf: Snapshot of MESSAGING_* config keys.
    :raises Exception: If messages cannot be delivered after kafka-python retries
    """
    try:
        producer = _get_kafka_producer(msg_conf)
        topic_prefix = msg_conf.get("MESSAGING_TOPIC_PREFIX", "cts.")
        for msg in msgs:
            event = msg.get("event", "event")
            topic = "%s%s" % (topic_prefix, event)
            producer.send(topic, msg)
        producer.flush()
    except Exception:
        _close_kafka_producer()
        raise


def _umb_send_msg(msgs, msg_conf):
    """Send message to Unified Message Bus with retry logic"""

    import proton
    from rhmsg.activemq.producer import AMQProducer

    def _send():
        """Inner function to send messages (will be retried on failure)"""
        amq_config = {
            "urls": msg_conf.get("MESSAGING_BROKER_URLS", []),
            "certificate": msg_conf.get("MESSAGING_CERT_FILE", ""),
            "private_key": msg_conf.get("MESSAGING_KEY_FILE", ""),
            "trusted_certificates": msg_conf.get("MESSAGING_CA_CERT", ""),
        }
        topic_prefix = msg_conf.get("MESSAGING_TOPIC_PREFIX", "cts.")
        with AMQProducer(**amq_config) as producer:
            for msg in msgs:
                event = msg.get("event", "event")
                topic = "%s%s" % (topic_prefix, event)
                producer.through_topic(topic)
                outgoing_msg = proton.Message()
                outgoing_msg.body = json.dumps(msg)
                producer.send(outgoing_msg)

    # Retry the send operation with exponential backoff
    _retry_with_backoff(_send)


def _get_messaging_backend(msg_conf):
    backend = msg_conf.get("MESSAGING_BACKEND", "")
    if backend == "kafka":
        return _kafka_send_msg
    elif backend == "rhmsg":
        return _umb_send_msg
    elif backend:
        raise ValueError("Unknown messaging backend {0}".format(backend))
    else:
        return None
