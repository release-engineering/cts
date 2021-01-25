===========
Development
===========

Code Convention
===============

The code must be well formatted via ``black`` and pass ``flake8`` checking.

Run ``tox -e black,flake8`` to do the check.

Install dependencies
====================

.. sourcecode:: none

    $ pip install -r requirements.txt

Initialize database
===================

.. sourcecode:: none

    $ ./create_sqlite_db

Start cts
=========

.. sourcecode:: none

    $ ./start_cts_from_here

Testing
=======

.. sourcecode:: none

    $ tox
