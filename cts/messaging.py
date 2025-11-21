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

import json
import time
from concurrent.futures import ThreadPoolExecutor
from logging import getLogger

from cts import conf

log = getLogger(__name__)

__all__ = ("publish",)

# Thread pool for async message publishing (single worker to serialize message sending)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cts-messaging")


def publish(msgs):
    """
    Publish messages to message broker asynchronously.

    Messages are published in a background thread to avoid blocking HTTP requests.
    Failures are logged but do not prevent the HTTP response from being sent.
    """
    backend = _get_messaging_backend()
    if backend is not None:

        def _send():
            try:
                backend(msgs)
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
                    f"UMB messaging attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay *= backoff_multiplier
            else:
                log.error(f"UMB messaging failed after {max_retries + 1} attempts: {e}")

    raise last_exception


def _umb_send_msg(msgs):
    """Send message to Unified Message Bus with retry logic"""

    import proton
    from rhmsg.activemq.producer import AMQProducer

    def _send():
        """Inner function to send messages (will be retried on failure)"""
        config = {
            "urls": conf.messaging_broker_urls,
            "certificate": conf.messaging_cert_file,
            "private_key": conf.messaging_key_file,
            "trusted_certificates": conf.messaging_ca_cert,
        }
        with AMQProducer(**config) as producer:
            for msg in msgs:
                event = msg.get("event", "event")
                topic = "%s%s" % (conf.messaging_topic_prefix, event)
                producer.through_topic(topic)
                outgoing_msg = proton.Message()
                outgoing_msg.body = json.dumps(msg)
                producer.send(outgoing_msg)

    # Retry the send operation with exponential backoff
    _retry_with_backoff(_send)


def _get_messaging_backend():
    if conf.messaging_backend == "rhmsg":
        return _umb_send_msg
    elif conf.messaging_backend:
        raise ValueError("Unknown messaging backend {0}".format(conf.messaging_backend))
    else:
        return None
