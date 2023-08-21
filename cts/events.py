# -*- coding: utf-8 -*-
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


from threading import Lock
import flask
from logging import getLogger
from sqlalchemy.orm import attributes

from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


log = getLogger()

_cache_lock = Lock()
_cached_composes = {}


def cache_composes_if_state_changed(session, flush_context):
    """Prepare outgoing messages when compose state is changed"""

    from cts.models import Compose

    composes = (
        item for item in (session.new | session.dirty) if isinstance(item, Compose)
    )

    with _cache_lock:
        for comp in composes:
            extra_args = {}
            if not attributes.get_history(comp, "id").unchanged:
                event = "compose-created"
            elif attributes.get_history(comp, "tags").added:
                event = "compose-tagged"
                # We change only single tag in the same time.
                extra_args["tag"] = attributes.get_history(comp, "tags").added[0].name
                extra_args["user_data"] = (
                    attributes.get_history(comp, "changes").added[0].user_data
                )
            elif attributes.get_history(comp, "tags").deleted:
                event = "compose-untagged"
                # We change only single tag in the same time.
                extra_args["tag"] = attributes.get_history(comp, "tags").deleted[0].name
                extra_args["user_data"] = (
                    attributes.get_history(comp, "changes").added[0].user_data
                )
            else:
                event = "compose-changed"

            if comp.id not in _cached_composes:
                _cached_composes[comp.id] = []
            msg = {
                "event": event,
                "compose": comp.json(),
            }
            if flask.g.user:
                extra_args["agent"] = flask.g.user.username
            else:
                extra_args["agent"] = None
            # Add telemetry information. This includes an extra key
            # traceparent.
            TraceContextTextMapPropagator().inject(extra_args)

            msg.update(extra_args)
            _cached_composes[comp.id].append(msg)

    log.debug(
        "Cached composes to be sent due to state changed: %s", _cached_composes.keys()
    )


def start_to_publish_messages(session):
    """Publish messages after data is committed to database successfully"""
    import cts.messaging as messaging

    with _cache_lock:
        msgs = []
        for compose_msgs in _cached_composes.values():
            msgs += compose_msgs
        log.debug("Sending messages: %s", msgs)
        if msgs:
            try:
                messaging.publish(msgs)
            except Exception:
                log.exception("Cannot publish message to bus.")
        _cached_composes.clear()
