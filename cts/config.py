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
import sys

from importlib.machinery import SourceFileLoader

import cts.logger as logger


def _is_pytest():
    return any(
        [
            "nosetests" in arg
            or "noserunner.py" in arg
            or "py.test" in arg
            or "pytest" in arg
            for arg in sys.argv
        ]
    )


def _is_developer_env():
    return os.environ.get("CTS_DEVELOPER_ENV", "").lower() in (
        "1",
        "on",
        "true",
        "y",
        "yes",
    )


def _use_repo_config_module(config_file):
    if _is_pytest() or _is_developer_env():
        return True
    try:
        with open(config_file):
            return False
    except (OSError, IOError):
        return True


def init_config(app, config_section=None):
    """
    Configure CTS
    """
    config_file = os.environ.get("CTS_CONFIG_FILE", "/etc/cts/config.py")

    if config_section is None:
        config_section = os.environ.get("CTS_CONFIG_SECTION")

    if config_section is None:
        if _is_pytest():
            config_section = "TestConfiguration"
        elif _is_developer_env():
            config_section = "DevConfiguration"
        else:
            try:
                with open(config_file):
                    config_section = "ProdConfiguration"
            except (OSError, IOError) as e:
                sys.stderr.write(
                    "WARN: Cannot open %s: %s\n" % (config_file, e.strerror)
                )
                sys.stderr.write("WARN: DevConfiguration will be used.\n")
                config_section = "DevConfiguration"

    if _use_repo_config_module(config_file):
        from conf import config as config_module
    else:
        try:
            config_module = SourceFileLoader(
                "cts_runtime_config", config_file
            ).load_module()
        except Exception:
            raise SystemError(
                "Configuration file {} was not found.".format(config_file)
            )

    try:
        config_section_obj = getattr(config_module, config_section)
    except AttributeError:
        raise SystemError(
            "Configuration section {} was not found.".format(config_section)
        )

    app.config.from_object(config_section_obj)
    _apply_defaults(app.config)
    _validate_config(app.config)


_CONFIG_DEFAULTS = {
    "ADMINS": {"groups": [], "users": []},
    "ALLOWED_BUILDERS": {"groups": [], "users": []},
    "OIDC_BASE_NAMESPACE": "https://pagure.io/cts/",
    "MESSAGING_TOPIC_PREFIX": "cts.",
}


def _apply_defaults(config):
    for key, default in _CONFIG_DEFAULTS.items():
        config.setdefault(key, default)
    config.setdefault("LOGIN_DISABLED", config.get("AUTH_BACKEND") in ("noauth", ""))
    raw_level = config.get("LOG_LEVEL")
    if isinstance(raw_level, str):
        config["LOG_LEVEL"] = logger.str_to_log_level(raw_level.lower())
    if config.get("LOG_FILE") is None:
        config["LOG_FILE"] = ""


def _validate_config(config):
    mechanism = config.get("AUTH_LDAP_BIND_MECHANISM", "gssapi")
    if isinstance(mechanism, str):
        mechanism = mechanism.lower()
        config["AUTH_LDAP_BIND_MECHANISM"] = mechanism
    if mechanism not in ("gssapi", "simple", "none"):
        raise ValueError(
            "Unsupported LDAP bind mechanism %r, supported values: "
            "gssapi, simple, none." % mechanism
        )
