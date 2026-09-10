# -*- coding: utf-8 -*-

from importlib.metadata import PackageNotFoundError, version as _version

try:
    version = _version("cts")
except PackageNotFoundError:
    version = "unknown"
