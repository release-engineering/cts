=================
Integration tests
=================

Integration tests validate the **built container image** against a real
PostgreSQL database, OIDC auth (Dex + OpenLDAP), and Kafka. They run in
Konflux CI after successful builds and can be reproduced locally with kind.

The Mermaid deployment diagram is in the
`README on GitHub <https://github.com/release-engineering/cts/blob/main/README.md#integration-tests>`_
(GitHub renders Mermaid there). The sections below describe the same layout in
prose.

Test suite
==========

``tests/test_integration_api.py`` uses pytest and plain HTTP (``urllib`` /
``requests``). Tests include:

- API root, about, composes, OpenAPI, tags, pagination, 404 handling
- Compose workflow (create, tag, respin) when write access is available
- OIDC auth (401/403/authorized writes) when ``AUTH_BACKEND`` is OIDC-enabled
- Kafka event assertions when ``KAFKA_URL`` is set

Tests run **inside the cluster** in CI (and in ``run-local.sh``) so they can
reach in-cluster DNS names (``cts``, ``dex``, ``kafka``) and trust the Dex CA
without port-forwarding.

Environment layout
==================

Each test run uses a dedicated Kubernetes namespace containing:

+------------------+----------------------------------------------------------+
| Component        | Role                                                     |
+==================+==========================================================+
| PostgreSQL       | CTS database; migrations via init container              |
+------------------+----------------------------------------------------------+
| OpenLDAP         | User directory for Dex                                   |
+------------------+----------------------------------------------------------+
| Dex              | OIDC provider (TLS, LDAP backend)                        |
+------------------+----------------------------------------------------------+
| Kafka            | Message bus for compose event assertions                 |
+------------------+----------------------------------------------------------+
| CTS              | Image under test; Apache + mod_wsgi on port 8080         |
+------------------+----------------------------------------------------------+
| cts-test-runner  | Ephemeral pod; installs pytest deps and runs the suite   |
+------------------+----------------------------------------------------------+

Manifests: ``integration-tests/manifests/``. Deploy scripts:
``integration-tests/scripts/``.

Konflux CI
==========

1. Build pipeline produces the CTS (and ldap-server) container images.
2. ``IntegrationTestScenario`` (``.tekton/cts-integration-test.yaml``) triggers
   ``.tekton/integration-test-eaas.yaml``.
3. EaaS provisions an ephemeral namespace and kubeconfig.
4. Pipeline deploys PostgreSQL, OpenLDAP, Dex, Kafka, and CTS.
5. A test-runner pod clones the repo and runs::

     pytest tests/test_integration_api.py

   with ``CTS_URL=http://cts:8080`` and related variables (see
   ``integration-tests/scripts/pytest-cmd.sh``).
6. EaaS tears down the namespace when the pipeline finishes.

Running locally
===============

From the repository root::

    ./integration-tests/run-local.sh

Prerequisites: kind, kubectl, podman or docker, openssl.

Options: ``--skip-build``, ``--keep-cluster``, ``--no-tests``. Set
``CONTAINER_ENGINE=docker`` to use Docker instead of podman with kind.

Point pytest at an existing deployment::

    CTS_URL=http://localhost:8080 pytest tests/test_integration_api.py -v -o addopts=

Use ``-o addopts=`` to disable the default coverage options from ``tox.ini``.

``tests/conftest.py`` bootstraps ``create_app()`` for unit tests only (when
``CTS_URL`` is unset). Integration runs set ``CTS_URL`` so the test runner does
not need the ``cts`` package or Flask dependencies.

Adding tests
============

Add ``test_*`` functions to ``tests/test_integration_api.py`` and use the
``http_client``, ``write_http_client``, or auth fixtures as appropriate. No
manual registration is required.

Related files
=============

- ``.tekton/integration-test-eaas.yaml`` — CI pipeline
- ``.tekton/README-INTEGRATION-TESTS.md`` — Konflux-specific notes
- ``integration-tests/run-local.sh`` — local kind workflow
