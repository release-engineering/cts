# -*- coding: utf-8 -*-

import logging

logging.basicConfig(level="DEBUG")

from cts import create_app

application = create_app(mode="full")
