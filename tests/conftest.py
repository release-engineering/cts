from cts import create_app

# Bootstrap the full application for unittest-based tests before modules
# capture stale configuration references.
create_app(mode="full")
