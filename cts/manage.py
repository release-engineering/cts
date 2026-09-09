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

from datetime import timedelta
import json
import logging
import os
import ssl

import click

from flask import current_app
from flask.cli import FlaskGroup
from werkzeug.serving import run_simple

import cts.models as models
from cts import create_app
from cts.extensions import db

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 5005


def _cli_config_section():
    return os.environ.get("CTS_CONFIG_SECTION")


def _web_config_section():
    if os.environ.get("CTS_CONFIG_SECTION"):
        return os.environ["CTS_CONFIG_SECTION"]
    if os.environ.get("CTS_DEVELOPER_ENV", "").lower() in (
        "1",
        "on",
        "true",
        "y",
        "yes",
    ):
        return "DevConfiguration"
    return "ProdConfiguration"


def _establish_ssl_context(config):
    if not config.get("SSL_ENABLED"):
        return None
    attributes = (
        "SSL_CERTIFICATE_FILE",
        "SSL_CERTIFICATE_KEY_FILE",
        "SSL_CA_CERTIFICATE_FILE",
    )

    for attribute in attributes:
        value = config.get(attribute)
        if not value:
            raise ValueError("%r could not be found" % attribute)
        if not os.path.exists(value):
            raise OSError("%s: %s file not found." % (attribute, value))

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    ssl_ctx.load_cert_chain(
        config["SSL_CERTIFICATE_FILE"], config["SSL_CERTIFICATE_KEY_FILE"]
    )
    ssl_ctx.verify_mode = ssl.CERT_OPTIONAL
    ssl_ctx.load_verify_locations(cafile=config["SSL_CA_CERTIFICATE_FILE"])
    return ssl_ctx


@click.group(
    cls=FlaskGroup,
    create_app=lambda: create_app(config_section=_cli_config_section()),
)
def cli():
    """Manage CTS application"""


@cli.command()
def generatelocalhostcert():
    """Creates a public/private key pair for message signing and the frontend"""
    from OpenSSL import crypto

    config = current_app.config
    key_file = config["SSL_CERTIFICATE_KEY_FILE"]
    cert_file_path = config["SSL_CERTIFICATE_FILE"]

    cert_key = crypto.PKey()
    cert_key.generate_key(crypto.TYPE_RSA, 2048)

    with open(key_file, "w") as f:
        os.chmod(key_file, 0o600)
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, cert_key))

    cert = crypto.X509()
    msg_cert_subject = cert.get_subject()
    msg_cert_subject.C = "US"
    msg_cert_subject.ST = "MA"
    msg_cert_subject.L = "Boston"
    msg_cert_subject.O = "Development"  # noqa
    msg_cert_subject.CN = "localhost"
    cert.set_serial_number(2)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(315360000)  # 10 years
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(cert_key)
    cert_extensions = [
        crypto.X509Extension(
            "keyUsage", True, "digitalSignature, keyEncipherment, nonRepudiation"
        ),
        crypto.X509Extension("extendedKeyUsage", True, "serverAuth"),
    ]
    cert.add_extensions(cert_extensions)
    cert.sign(cert_key, "sha256")

    with open(cert_file_path, "w") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))


@cli.command()
@click.option("-h", "--host", default=_DEFAULT_HOST, help="Bind to this address")
@click.option(
    "-p", "--port", type=int, default=_DEFAULT_PORT, help="Listen on this port"
)
@click.option("-d", "--debug", is_flag=True, default=False, help="Debug mode")
def runssl(host, port, debug):
    """Runs the Flask app with the HTTPS settings configured in config.py"""
    logging.info("Starting CTS frontend")

    app = create_app(config_section=_web_config_section())
    ssl_ctx = _establish_ssl_context(app.config)
    run_simple(host, port, app, use_debugger=debug, ssl_context=ssl_ctx)


@cli.command()
@click.option(
    "-t",
    "--timeout",
    type=int,
    default=6,
    help="Timeout period in hours for retagging the stale composes",
)
def check_stale_requests(timeout):
    """Check the stale requests in the database"""

    from flask import g

    try:
        timeout_h = timedelta(hours=timeout)
        logging.info(
            "Checking stale composes with requested tag within {} hours".format(timeout)
        )
        # Get the composes with -requested tag
        query = models.Compose.query.outerjoin(models.Compose.tags, aliased=True)
        composes = query.filter(models.Tag.name.contains("requested")).all()
        system_user = models.User.find_user_by_name(username="SYSTEM")
        if not system_user:
            system_user = models.User.create_user(username="SYSTEM")
            logging.info("New SYSTEM User is created in database.")
            db.session.commit()
        g.user = system_user
        for compose in composes:
            for retag in compose.retag_stale_composes(g.user.username, timeout_h):
                logging.info(
                    "Checking compose:{} for tag {} is done".format(
                        compose.id, retag.name
                    )
                )
        logging.info("Checking for stale requests is done")

    except BaseException as e:
        logging.error("Error occured while retagging compose:{}".format(compose.id))
        raise e


@cli.command()
def openapispec():
    """Dump OpenAPI specification"""
    app = create_app(config_section=_web_config_section())
    print(json.dumps(app.openapispec.to_dict(), indent=2))


if __name__ == "__main__":
    cli()
