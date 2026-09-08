===========
Development
===========

Developer setup, unit testing, and integration testing are documented in the
`README on GitHub <https://github.com/release-engineering/cts/blob/main/README.md>`_.

Quick reference
===============

Code style
----------

Format with ``black``, lint with ``flake8``, and scan with ``bandit``::

    tox -e black,flake8,bandit

Unit tests
----------

Run the unit test suite with coverage::

    tox -e py3

Build documentation
-------------------

Build the Sphinx HTML docs locally::

    tox -e docs

Output is written to ``docs/_build/html/``.

Local CTS
---------

::

    pip install -r requirements.txt
    ./create_sqlite_db
    ./start_cts_from_here

Integration tests
-----------------

::

    ./integration-tests/run-local.sh

See :doc:`integration` for the full integration-test environment and CI flow.
