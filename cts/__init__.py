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
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from werkzeug.exceptions import BadRequest, NotFound as WerkzeugNotFound, Unauthorized

from cts._version import version  # noqa: F401
from cts.config import init_config
from cts.errors import Forbidden, NotFound
from cts.extensions import db, login_manager, migrate, migrations_dir
from cts.logger import init_logging
from cts.proxy import ReverseProxy

# conf and log must be defined before importing auth/views, which
# read them at import time via ``from cts import conf, log``.
conf = None
log = getLogger(__name__)

from cts.auth import init_auth  # noqa: E402
from cts.views import register_views  # noqa: E402


def _sync_conf_binding():
    """Rebind conf in modules that imported it before initialization."""
    import sys

    import cts.auth

    cts.auth.conf = conf
    if "cts.views" in sys.modules:
        import cts.views

        cts.views.conf = conf


def create_app(config_section=None):
    """Create and configure the CTS Flask application.

    :param str config_section: Optional configuration class name, for example
        ``ProdConfiguration`` or ``DevConfiguration``.  When omitted the
        section is resolved from the environment and runtime context
        (see :func:`cts.config.init_config`).
    """
    global conf

    app = Flask(__name__)
    app.wsgi_app = ReverseProxy(app.wsgi_app)

    conf = init_config(app, config_section=config_section)
    _sync_conf_binding()
    db.init_app(app)
    init_logging(conf)
    login_manager.init_app(app)
    migrate.init_app(app, db, directory=migrations_dir)

    import cts.models  # noqa: F401

    auth_backend = conf.auth_backend
    if auth_backend:
        init_auth(login_manager, auth_backend)

    register_views(app)
    _register_error_handlers(app)
    _setup_telemetry(app)

    return app


def _json_error(status, error, message):
    response = jsonify({"status": status, "error": error, "message": message})
    response.status_code = status
    return response


def _register_error_handlers(app):
    @app.errorhandler(NotFound)
    @app.errorhandler(WerkzeugNotFound)
    def notfound_error(e):
        """Flask error handler for NotFound exceptions"""
        try:
            msg = e.args[0]
        except IndexError:
            msg = "The requested URL was not found on the server."
        return _json_error(404, "Not Found", msg)

    @app.errorhandler(Unauthorized)
    def unauthorized_error(e):
        """Flask error handler for Unauthorized exceptions"""
        return _json_error(401, "Unauthorized", e.description)

    @app.errorhandler(Forbidden)
    def forbidden_error(e):
        """Flask error handler for Forbidden exceptions"""
        return _json_error(403, "Forbidden", e.args[0])

    @app.errorhandler(BadRequest)
    def badrequest_error(e):
        """Flask error handler for RuntimeError exceptions"""
        return _json_error(400, "Bad Request", e.get_description())

    @app.errorhandler(ValueError)
    def validationerror_error(e):
        """Flask error handler for ValueError exceptions"""
        return _json_error(400, "Bad Request", str(e))

    @app.errorhandler(Exception)
    def internal_server_error(e):
        """Flask error handler for RuntimeError exceptions"""
        log.exception("Internal server error: %s", e)
        return _json_error(500, "Internal Server Error", str(e))


def _setup_telemetry(app):
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "cts"}))
    trace.set_tracer_provider(provider)
    exporter_url = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if exporter_url == "console":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    elif exporter_url:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

    FlaskInstrumentor().instrument_app(app, tracer_provider=provider)
    if "CTS_INSTRUMENT_DATABASE" in os.environ:
        SQLAlchemyInstrumentor().instrument()
