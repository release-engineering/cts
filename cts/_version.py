# -*- coding: utf-8 -*-

import pkg_resources

try:
    version = pkg_resources.get_distribution("cts").version
except pkg_resources.DistributionNotFound:
    version = "unknown"
