# -*- coding: utf-8 -*-

import logging

logging.basicConfig(level="DEBUG")

from cts import create_app  # noqa: E402

application = create_app(config_section="ProdConfiguration")
