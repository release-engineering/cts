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
from logging import getLogger

from flask import Flask, jsonify
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from werkzeug.exceptions import BadRequest, Unauthorized, NotFound as WerkzeugNotFound

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor

from cts.logger import init_logging
from cts.config import init_config
from cts.proxy import ReverseProxy
from cts.errors import NotFound, Forbidden

import pkg_resources

try:
    version = pkg_resources.get_distribution("cts").version
except pkg_resources.DistributionNotFound:
    version = "unknown"

app = Flask(__name__)
app.wsgi_app = ReverseProxy(app.wsgi_app)

conf = init_config(app)

db = SQLAlchemy(app)

init_logging(conf)
log = getLogger(__name__)

login_manager = LoginManager()
login_manager.init_app(app)

from cts import views  # noqa

from cts.auth import init_auth  # noqa

init_auth(login_manager, conf.auth_backend)

# Set up telemetry exporter if configured.
provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "cts"}))
trace.set_tracer_provider(provider)
exporter_url = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
if exporter_url == "console":
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
elif exporter_url:
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

tracer = trace.get_tracer(__name__)

# Initialize Flask drop-in instrumentation middleware
FlaskInstrumentor().instrument_app(app, tracer_provider=provider)


def json_error(status, error, message):
    response = jsonify({"status": status, "error": error, "message": message})
    response.status_code = status
    return response


@app.errorhandler(NotFound)
@app.errorhandler(WerkzeugNotFound)
def notfound_error(e):
    """Flask error handler for NotFound exceptions"""
    try:
        msg = e.args[0]
    except IndexError:
        msg = "The requested URL was not found on the server."
    return json_error(404, "Not Found", msg)


@app.errorhandler(Unauthorized)
def unauthorized_error(e):
    """Flask error handler for Unauthorized exceptions"""
    return json_error(401, "Unauthorized", e.description)


@app.errorhandler(Forbidden)
def forbidden_error(e):
    """Flask error handler for Forbidden exceptions"""
    return json_error(403, "Forbidden", e.args[0])


@app.errorhandler(BadRequest)
def badrequest_error(e):
    """Flask error handler for RuntimeError exceptions"""
    return json_error(400, "Bad Request", e.get_description())


@app.errorhandler(ValueError)
def validationerror_error(e):
    """Flask error handler for ValueError exceptions"""
    return json_error(400, "Bad Request", str(e))


@app.errorhandler(Exception)
def internal_server_error(e):
    """Flask error handler for RuntimeError exceptions"""
    log.exception("Internal server error: %s", e)
    return json_error(500, "Internal Server Error", str(e))
