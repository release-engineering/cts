import os

if not os.environ.get("CTS_URL"):
    import cts

    # Bootstrap the application for unittest-based tests.  Store the
    # instance as ``cts.app`` so that test helpers importing
    # ``from cts import app`` get the configured application.
    # Push an app context so that extensions like SQLAlchemy can
    # resolve the active application.
    _app = cts.create_app()
    cts.app = _app
    _app.app_context().push()
