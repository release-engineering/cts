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

from datetime import datetime, timedelta
import logging
import os
import ssl

import click
import flask_migrate

from flask.cli import FlaskGroup
from werkzeug.serving import run_simple

from cts import app, conf, db, models


def _establish_ssl_context():
    if not conf.ssl_enabled:
        return None
    # First, do some validation of the configuration
    attributes = (
        "ssl_certificate_file",
        "ssl_certificate_key_file",
        "ssl_ca_certificate_file",
    )

    for attribute in attributes:
        value = getattr(conf, attribute, None)
        if not value:
            raise ValueError("%r could not be found" % attribute)
        if not os.path.exists(value):
            raise OSError("%s: %s file not found." % (attribute, value))

    # Then, establish the ssl context and return it
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    ssl_ctx.load_cert_chain(conf.ssl_certificate_file, conf.ssl_certificate_key_file)
    ssl_ctx.verify_mode = ssl.CERT_OPTIONAL
    ssl_ctx.load_verify_locations(cafile=conf.ssl_ca_certificate_file)
    return ssl_ctx


@click.group(cls=FlaskGroup, create_app=lambda *args, **kwargs: app)
def cli():
    """Manage CTS application"""


migrations_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "migrations")
flask_migrate.Migrate(app, db, directory=migrations_dir)


@cli.command()
def generatelocalhostcert():
    """Creates a public/private key pair for message signing and the frontend"""
    from OpenSSL import crypto

    cert_key = crypto.PKey()
    cert_key.generate_key(crypto.TYPE_RSA, 2048)

    with open(conf.ssl_certificate_key_file, "w") as cert_key_file:
        os.chmod(conf.ssl_certificate_key_file, 0o600)
        cert_key_file.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, cert_key))

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

    with open(conf.ssl_certificate_file, "w") as cert_file:
        cert_file.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))


@cli.command()
@click.option("-h", "--host", default=conf.host, help="Bind to this address")
@click.option("-p", "--port", type=int, default=conf.port, help="Listen on this port")
@click.option("-d", "--debug", is_flag=True, default=conf.debug, help="Debug mode")
def runssl(host=conf.host, port=conf.port, debug=conf.debug):
    """Runs the Flask app with the HTTPS settings configured in config.py"""
    logging.info("Starting CTS frontend")

    ssl_ctx = _establish_ssl_context()
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
        # Get the last tagged time of the compose
        last_change = models.ComposeChange.query.filter_by(
            compose_id=compose.id, action="tagged"
        ).all()[-1]
        if datetime.utcnow() - last_change.time > timeout_h:
            tag_name = last_change.message.split()[3][1:-1]
            # Untag compose
            compose.untag(g.user.username, tag_name)
            db.session.commit()
            logging.info("Compose:{} is succesfully untagged".format(compose.id))

            # Tag compose again with -requested
            compose.tag(g.user.username, tag_name)
            db.session.commit()
            logging.info("Compose:{} is tagged as {}".format(compose.id, tag_name))


if __name__ == "__main__":
    cli()
