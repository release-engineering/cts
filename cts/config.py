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

from cts import logger


def init_config(app):
    """
    Configure CTS
    """
    config_module = None
    config_file = "/etc/cts/config.py"
    config_section = "DevConfiguration"

    # automagically detect production environment:
    #   - existing and readable config_file presets ProdConfiguration
    try:
        with open(config_file):
            config_section = "ProdConfiguration"
    except (OSError, IOError) as e:
        # Use stderr here, because logging is not initialized so far...
        sys.stderr.write("WARN: Cannot open %s: %s\n" % (config_file, e.strerror))
        sys.stderr.write("WARN: DevConfiguration will be used.\n")

    # try getting config_file from os.environ
    if "CTS_CONFIG_FILE" in os.environ:
        config_file = os.environ["CTS_CONFIG_FILE"]
    # try getting config_section from os.environ
    if "CTS_CONFIG_SECTION" in os.environ:
        config_section = os.environ["CTS_CONFIG_SECTION"]
    # TestConfiguration shall only be used for running tests, otherwise...
    if any(
        [
            "nosetests" in arg
            or "noserunner.py" in arg
            or "py.test" in arg
            or "pytest" in arg
            for arg in sys.argv
        ]
    ):
        config_section = "TestConfiguration"
        from conf import config

        config_module = config
    # ...CTS_DEVELOPER_ENV has always the last word
    # and overrides anything previously set before!
    # In any of the following cases, use configuration directly from CTS
    # package -> /conf/config.py.

    elif "CTS_DEVELOPER_ENV" in os.environ and os.environ[
        "CTS_DEVELOPER_ENV"
    ].lower() in ("1", "on", "true", "y", "yes"):
        config_section = "DevConfiguration"
        from conf import config

        config_module = config
    # try loading configuration from file
    if not config_module:
        try:
            config_module = SourceFileLoader(
                "cts_runtime_config", config_file
            ).load_module()
        except Exception:
            raise SystemError(
                "Configuration file {} was not found.".format(config_file)
            )

    # finally configure CTS
    config_section_obj = getattr(config_module, config_section)
    conf = Config(config_section_obj)
    app.config.from_object(config_section_obj)
    return conf


class Config(object):
    """Class representing the CTS configuration."""

    _defaults = {
        "debug": {"type": bool, "default": False, "desc": "Debug mode"},
        "log_backend": {"type": str, "default": None, "desc": "Log backend"},
        "log_file": {"type": str, "default": "", "desc": "Path to log file"},
        "log_level": {"type": str, "default": 0, "desc": "Log level"},
        "admins": {
            "type": dict,
            "default": {"groups": [], "users": []},
            "desc": "Admin groups and users.",
        },
        "allowed_builders": {
            "type": dict,
            "default": {"groups": {}, "users": {}},
            "desc": "Groups and users that are allowed to add new composes.",
        },
        "auth_backend": {
            "type": str,
            "default": "",
            "desc": "Select which authentication backend is enabled and work "
            "with frond-end authentication together.",
        },
        "auth_openidc_userinfo_uri": {
            "type": str,
            "default": "",
            "desc": "UserInfo endpoint to get user information from FAS.",
        },
        "auth_openidc_required_scopes": {
            "type": list,
            "default": [],
            "desc": "Required scopes for submitting request to run new compose.",
        },
        "auth_ldap_server": {
            "type": str,
            "default": "",
            "desc": "Server URL to query user's groups.",
        },
        "auth_ldap_groups": {
            "type": list,
            "default": [],
            "desc": "List of pairs (search base, filter pattern) to query user's groups from LDAP server.",
        },
        "messaging_backend": {
            "type": str,
            "default": "",
            "desc": "Messaging backend, rhmsg or fedora-messaging.",
        },
        "messaging_broker_urls": {
            "type": list,
            "default": [],
            "desc": "List of messaging broker URLs.",
        },
        "messaging_cert_file": {
            "type": str,
            "default": "",
            "desc": "Path to certificate file used to authenticate CTS by broker.",
        },
        "messaging_key_file": {
            "type": str,
            "default": "",
            "desc": "Path to private key file used to authenticate CTS by broker.",
        },
        "messaging_ca_cert": {
            "type": str,
            "default": "",
            "desc": "Path to trusted CA certificate bundle.",
        },
        "messaging_topic_prefix": {
            "type": str,
            "default": "cts.",
            "desc": "Prefix for AMQP or fedora-messaging messages.",
        },
        "oidc_base_namespace": {
            "type": str,
            "default": "https://pagure.io/cts/",
            "desc": "Base namespace of OIDC scopes.",
        },
    }

    def __init__(self, conf_section_obj):
        """
        Initialize the Config object with defaults and then override them
        with runtime values.
        """

        # read items from conf and set
        for key in dir(conf_section_obj):
            # skip keys starting with underscore
            if key.startswith("_"):
                continue
            # set item (lower key)
            self.set_item(key.lower(), getattr(conf_section_obj, key))

        # set item from defaults if the item is not set
        for name, values in self._defaults.items():
            if hasattr(self, name):
                continue
            self.set_item(name, values["default"])

        # Used by Flask-Login to disable the @login_required decorator
        self.login_disabled = self.auth_backend == "noauth"

    def set_item(self, key, value):
        """
        Set value for configuration item. Creates the self._key = value
        attribute and self.key property to set/get/del the attribute.
        """
        if key == "set_item" or key.startswith("_"):
            raise Exception("Configuration item's name is not allowed: %s" % key)

        # Create the empty self._key attribute, so we can assign to it.
        setattr(self, "_" + key, None)

        # Create self.key property to access the self._key attribute.
        # Use the setifok_func if available for the attribute.
        setifok_func = "_setifok_{}".format(key)
        if hasattr(self, setifok_func):
            setx = lambda self, val: getattr(self, setifok_func)(val)
        else:
            setx = lambda self, val: setattr(self, "_" + key, val)
        getx = lambda self: getattr(self, "_" + key)
        delx = lambda self: delattr(self, "_" + key)
        setattr(Config, key, property(getx, setx, delx))

        # managed/registered configuration items
        if key in self._defaults:
            # type conversion for configuration item
            convert = self._defaults[key]["type"]
            if convert in [bool, int, list, str, set, dict, float]:
                try:
                    # Do no try to convert None...
                    if value is not None:
                        value = convert(value)
                except Exception:
                    raise TypeError(
                        "Configuration value conversion failed for name: %s" % key
                    )
            # unknown type/unsupported conversion
            elif convert is not None:
                raise TypeError(
                    "Unsupported type %s for configuration item name: %s"
                    % (convert, key)
                )

        # Set the attribute to the correct value
        setattr(self, key, value)

    #
    # Register your _setifok_* handlers here
    #

    def _setifok_log_backend(self, s):
        if s is None:
            self._log_backend = "console"
        elif s not in logger.supported_log_backends():
            raise ValueError("Unsupported log backend")
        self._log_backend = str(s)

    def _setifok_log_file(self, s):
        if s is None:
            self._log_file = ""
        else:
            self._log_file = str(s)

    def _setifok_log_level(self, s):
        level = str(s).lower()
        self._log_level = logger.str_to_log_level(level)
