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

import os
import tempfile

from prometheus_client.core import GaugeMetricFamily
from prometheus_client import (  # noqa: F401
    ProcessCollector,
    CollectorRegistry,
    multiprocess,
)

from cts import db

# This environment variable should be set if deployment uses multiple
# processes.
if not os.environ.get("prometheus_multiproc_dir"):
    os.environ.setdefault("prometheus_multiproc_dir", tempfile.mkdtemp())


registry = CollectorRegistry()
ProcessCollector(registry=registry)
multiprocess.MultiProcessCollector(registry)


class ComposesCollector(object):
    def composes_total(self):
        """
        Returns `composes_total` GaugeMetricFamily with number of composes
        for each tag.
        """
        counter = GaugeMetricFamily(
            "composes_total",
            "Number of tagged composes",
            labels=["tag"],
        )
        rs = db.session.execute(
            "SELECT COUNT(composes.id), tags.name FROM composes JOIN (tags_to_composes JOIN tags ON tags.id = tags_to_composes.tag_id) ON composes.id = tags_to_composes.compose_id GROUP BY tags.name"
        ).fetchall()
        for tag in rs:
            # First element is the number of occurence of tag
            # Second element is the tag name
            counter.add_metric([tag[1]], tag[0])
        return counter

    def collect(self):
        yield self.composes_total()


registry.register(ComposesCollector())
