"""
Integration tests for CTS API endpoints.

Run with pytest by setting the CTS_URL environment variable:

  CTS_URL=http://localhost:5005 pytest tests/test_integration_api.py -v

In CI, the tests run in a pod deployed to the same namespace as the CTS service,
so they can access it directly via: http://cts:5005

For OIDC auth tests, set AUTH_BACKEND=openidc or AUTH_BACKEND=oidc_or_kerberos.
These tests are skipped when AUTH_BACKEND is "noauth" or unset.
"""

import json
import os
import ssl
import urllib.parse
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

import pytest


def _make_ssl_context():
    """Return an ssl.SSLContext that trusts the CA in REQUESTS_CA_BUNDLE (if set).

    urllib.request.urlopen does not honour the REQUESTS_CA_BUNDLE environment
    variable (only the *requests* library does).  When the integration tests run
    against a Dex instance that uses a self-signed certificate, we need to load
    the CA cert explicitly so that the ROPC token requests succeed.
    """
    ca_bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if ca_bundle:
        ctx = ssl.create_default_context(cafile=ca_bundle)
    else:
        ctx = ssl.create_default_context()
    return ctx


class HTTPClient:
    """Simple HTTP client for making requests to the CTS API"""

    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    def _prepare_request(self, req):
        """Hook for subclasses to modify the request before it is sent."""

    def _request(self, method, path, json_data=None):
        """Make HTTP request with specified method"""
        url = f"{self.base_url}{path}"
        req = Request(url, method=method)
        self._prepare_request(req)
        if json_data:
            req.add_header("Content-Type", "application/json")
            req.data = json.dumps(json_data).encode("utf-8")

        try:
            with urlopen(req, timeout=10) as response:
                data = response.read()
                if response.headers.get("Content-Type", "").startswith(
                    "application/json"
                ):
                    return response.status, json.loads(data)
                return response.status, data.decode("utf-8")
        except HTTPError as e:
            # Try to read error body
            try:
                error_data = e.read()
                if e.headers.get("Content-Type", "").startswith("application/json"):
                    return e.code, json.loads(error_data)
                return e.code, error_data.decode("utf-8")
            except Exception:
                return e.code, None
        except URLError as e:
            raise Exception(f"Failed to connect to {url}: {e}")

    def get(self, path):
        """Make HTTP GET request"""
        return self._request("GET", path)

    def post(self, path, json_data):
        """Make HTTP POST request"""
        return self._request("POST", path, json_data)

    def patch(self, path, json_data):
        """Make HTTP PATCH request"""
        return self._request("PATCH", path, json_data)

    def delete(self, path):
        """Make HTTP DELETE request"""
        return self._request("DELETE", path)


class AuthHTTPClient(HTTPClient):
    """HTTP client that injects an Authorization: Bearer header on every request."""

    def __init__(self, base_url, token):
        super().__init__(base_url)
        self.token = token

    def _prepare_request(self, req):
        req.add_header("Authorization", f"Bearer {self.token}")


def _get_oidc_token(username, password):
    """Obtain an OIDC access token from Dex via the Resource Owner Password Credentials grant."""
    dex_base_url = os.environ.get("DEX_URL", "https://dex:5556")
    dex_token_url = f"{dex_base_url}/token"
    payload = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": "cts-integration",
            "client_secret": "cts-integration-secret",
            "username": username,
            "password": password,
            "scope": "openid email",
        }
    ).encode("utf-8")

    req = Request(dex_token_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlopen(req, timeout=10, context=_make_ssl_context()) as resp:
            token_data = json.loads(resp.read())
            return token_data["access_token"]
    except HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise Exception(
            f"Failed to obtain token for {username}: HTTP {e.code}: {error_body}"
        )


def _is_oidc_backend():
    """Return True when AUTH_BACKEND is set to an OIDC-enabled value."""
    return os.environ.get("AUTH_BACKEND") in ("openidc", "oidc_or_kerberos")


@pytest.fixture(scope="module")
def http_client():
    """HTTP client fixture that reads CTS_URL from environment"""
    base_url = os.environ.get("CTS_URL")

    if not base_url:
        pytest.skip("Must set CTS_URL environment variable")

    print(f"\nConnecting to CTS at: {base_url}")
    return HTTPClient(base_url=base_url)


@pytest.fixture(scope="module")
def write_http_client():
    """HTTP client with write access.

    Returns an AuthHTTPClient authenticated as 'builder' when AUTH_BACKEND is an
    OIDC-enabled value (openidc or oidc_or_kerberos), or a plain HTTPClient when
    running in noauth mode.  Workflow tests that POST, PATCH, or DELETE should use
    this fixture so they work in both configurations.
    """
    base_url = os.environ.get("CTS_URL")
    if not base_url:
        pytest.skip("Must set CTS_URL environment variable")

    if _is_oidc_backend():
        token = _get_oidc_token("builder@example.com", "password")
        return AuthHTTPClient(base_url=base_url, token=token)

    return HTTPClient(base_url=base_url)


@pytest.fixture(scope="module")
def auth_http_client_builder():
    """AuthHTTPClient authenticated as the 'builder' user (has ALLOWED_BUILDERS access)."""
    if not _is_oidc_backend():
        pytest.skip("OIDC auth tests require AUTH_BACKEND=openidc or oidc_or_kerberos")

    base_url = os.environ.get("CTS_URL")
    if not base_url:
        pytest.skip("Must set CTS_URL environment variable")

    token = _get_oidc_token("builder@example.com", "password")
    return AuthHTTPClient(base_url=base_url, token=token)


@pytest.fixture(scope="module")
def auth_http_client_readonly():
    """AuthHTTPClient authenticated as the 'readonly' user (no write permissions)."""
    if not _is_oidc_backend():
        pytest.skip("OIDC auth tests require AUTH_BACKEND=openidc or oidc_or_kerberos")

    base_url = os.environ.get("CTS_URL")
    if not base_url:
        pytest.skip("Must set CTS_URL environment variable")

    token = _get_oidc_token("readonly@example.com", "password")
    return AuthHTTPClient(base_url=base_url, token=token)


def _create_compose_info(
    release_short, release_version, date, compose_type="test", respin=1
):
    """Helper to create a properly structured compose_info object"""
    compose_id = f"{release_short}-{release_version}-{date}.{compose_type[0]}.{respin}"
    return {
        "header": {"version": "1.2", "type": "productmd.composeinfo"},
        "payload": {
            "compose": {
                "id": compose_id,
                "type": compose_type,
                "date": date,
                "respin": respin,
            },
            "release": {
                "name": release_short,
                "short": release_short,
                "version": release_version,
                "is_layered": False,
                "type": "ga",
                "internal": False,
            },
            "variants": {},
        },
    }


class CTSClient:
    """Combines an HTTP client with an optional Kafka consumer.

    The Kafka consumer is ``None`` when ``KAFKA_URL`` is not set, in which
    case all Kafka assertions are silently skipped so tests run in both
    environments without modification.
    """

    def __init__(self, http_client, kafka_consumer=None):
        self.http = http_client
        self.kafka = kafka_consumer

    def _assert_kafka_message(self, topic, event_name, compose_id):
        """Consume one Kafka message and assert it matches the expected event."""
        _assert_compose_message(self.kafka, topic, event_name, compose_id)

    def create_tag(self, name, description, documentation):
        """Create a tag and return the response data."""
        tag_data = {
            "name": name,
            "description": description,
            "documentation": documentation,
        }
        status, data = self.http.post("/api/1/tags/", tag_data)
        assert status == 200, f"Failed to create tag: {data}"
        assert isinstance(data, dict)
        assert data["name"] == name
        assert "id" in data
        return data

    def _manage_tag_user(self, tag_id, action, username):
        """Internal helper to manage tag users (taggers/untaggers)."""
        status, data = self.http.patch(
            f"/api/1/tags/{tag_id}", {"action": action, "username": username}
        )
        assert status == 200, f"Failed to {action}: {data}"

        list_name = action.rsplit("_", 1)[1] + "s"

        if action.startswith("add_"):
            assert username in data[list_name], f"Expected {username} in {list_name}"
        else:
            assert (
                username not in data[list_name]
            ), f"Expected {username} not in {list_name}"

        return data

    def add_tagger(self, tag_id, username):
        """Add a tagger to a tag and return the response data."""
        return self._manage_tag_user(tag_id, "add_tagger", username)

    def remove_tagger(self, tag_id, username):
        """Remove a tagger from a tag and return the response data."""
        return self._manage_tag_user(tag_id, "remove_tagger", username)

    def add_untagger(self, tag_id, username):
        """Add an untagger to a tag and return the response data."""
        return self._manage_tag_user(tag_id, "add_untagger", username)

    def remove_untagger(self, tag_id, username):
        """Remove an untagger from a tag and return the response data."""
        return self._manage_tag_user(tag_id, "remove_untagger", username)

    def import_compose(
        self,
        release_short,
        release_version,
        date,
        compose_type="test",
        respin=1,
    ):
        """Import a compose and return the response data.

        Also asserts that CTS published a ``compose-created`` Kafka message
        when a Kafka consumer is configured.
        """
        compose_info = _create_compose_info(
            release_short, release_version, date, compose_type, respin
        )
        status, data = self.http.post(
            "/api/1/composes/", {"compose_info": compose_info}
        )
        assert status == 200, f"Failed to import compose: {data}"
        assert isinstance(data, dict)
        assert "payload" in data
        assert "compose" in data["payload"]
        compose_id = data["payload"]["compose"]["id"]
        self._assert_kafka_message("cts.compose-created", "compose-created", compose_id)
        return data

    def tag_compose(self, compose_id, tag_name):
        """Tag a compose and return the response data.

        Also asserts that CTS published a ``compose-tagged`` Kafka message
        when a Kafka consumer is configured.
        """
        status, data = self.http.patch(
            f"/api/1/composes/{compose_id}", {"action": "tag", "tag": tag_name}
        )
        assert status == 200, f"Failed to tag compose: {data}"
        assert tag_name in data.get("tags", [])
        self._assert_kafka_message("cts.compose-tagged", "compose-tagged", compose_id)
        return data

    def untag_compose(self, compose_id, tag_name):
        """Untag a compose and return the response data.

        Also asserts that CTS published a ``compose-untagged`` Kafka message
        when a Kafka consumer is configured.
        """
        status, data = self.http.patch(
            f"/api/1/composes/{compose_id}", {"action": "untag", "tag": tag_name}
        )
        assert status == 200, f"Failed to untag compose: {data}"
        assert tag_name not in data.get("tags", [])
        self._assert_kafka_message(
            "cts.compose-untagged", "compose-untagged", compose_id
        )
        return data


@pytest.fixture(scope="module")
def cts_client(write_http_client, kafka_consumer):
    """CTSClient wrapping the write HTTP client and the Kafka consumer."""
    return CTSClient(write_http_client, kafka_consumer)


@pytest.fixture(scope="module")
def cts_auth_client(auth_http_client_builder, kafka_consumer):
    """CTSClient wrapping the authenticated builder HTTP client and the Kafka consumer."""
    return CTSClient(auth_http_client_builder, kafka_consumer)


# Tests


def test_api_root(http_client):
    """Test that API root endpoint responds with documentation"""
    status, data = http_client.get("/api/1/")
    assert status == 200
    # API root returns HTML documentation page
    assert isinstance(
        data, str
    ), f"Expected HTML response (str), got {type(data).__name__}"
    assert "<!DOCTYPE html>" in data or "<html" in data, "Expected HTML content"


def test_about_endpoint(http_client):
    """Test the /about endpoint returns version information"""
    status, data = http_client.get("/api/1/about/")
    assert status == 200
    assert isinstance(data, dict)
    assert "version" in data
    print(f"  CTS version: {data['version']}")


def test_composes_list(http_client):
    """Test listing composes endpoint"""
    status, data = http_client.get("/api/1/composes/")
    assert status == 200
    assert isinstance(data, dict)
    assert "items" in data
    print(f"  Found {len(data['items'])} composes")


def test_composes_pagination(cts_client):
    """Test that pagination parameters work correctly"""
    # Import 3 test composes.  Kafka assertions are included via cts_client.
    compose_ids = []
    for i in range(1, 4):
        response = cts_client.import_compose(
            "PaginationTest",
            "1.0",
            f"2025010{i}",
        )
        compose_ids.append(response["payload"]["compose"]["id"])

    print(f"  Imported {len(compose_ids)} composes for pagination test")

    # Test page 1 with per_page=2
    status, data = cts_client.http.get("/api/1/composes/?page=1&per_page=2")
    assert status == 200
    assert isinstance(data, dict)
    assert "items" in data
    assert "meta" in data
    assert (
        len(data["items"]) == 2
    ), f"Expected exactly 2 items on page 1, got {len(data['items'])}"
    assert data["meta"]["per_page"] == 2
    assert data["meta"]["page"] == 1
    total = data["meta"]["total"]
    print(f"  Page 1 (per_page=2): {len(data['items'])} items, total: {total}")

    # Test page 2 with per_page=2 - should have 1 item (we imported 3 total)
    status, data = cts_client.http.get("/api/1/composes/?page=2&per_page=2")
    assert status == 200
    assert "items" in data
    assert (
        len(data["items"]) >= 1
    ), f"Expected at least 1 item on page 2, got {len(data['items'])}"
    assert data["meta"]["page"] == 2
    print(f"  Page 2 (per_page=2): {len(data['items'])} items")
    print("  ✓ Pagination working correctly with per_page=2")


def test_openapi_spec(http_client):
    """Test that OpenAPI specification is accessible"""
    status, data = http_client.get("/static/openapispec.json")
    assert status == 200
    assert isinstance(data, dict)
    assert "paths" in data
    print(f"  API has {len(data['paths'])} endpoints")


def test_tags_endpoint(http_client):
    """Test tags listing endpoint"""
    status, data = http_client.get("/api/1/tags/")
    assert status == 200
    assert isinstance(data, dict)


def test_404_handling(http_client):
    """Test that non-existent endpoints return 404"""
    status, _ = http_client.get("/api/1/nonexistent/")
    assert status == 404


# Workflow tests


def test_workflow_tag_creation(cts_client):
    """Test creating a tag and managing taggers/untaggers"""
    # Step 1: Create a tag
    data = cts_client.create_tag(
        "integration-test-tag",
        "Tag created during integration testing",
        "https://example.com/docs/integration-test",
    )
    tag_id = data["id"]
    print(f"  1. Created tag: {data['name']} (ID: {tag_id})")

    # Verify initial state - no taggers/untaggers
    assert data["taggers"] == []
    assert data["untaggers"] == []
    print(f"  2. Initial taggers: {data['taggers']}, untaggers: {data['untaggers']}")

    # Step 2: Add a tagger
    data = cts_client.add_tagger(tag_id, "test-user")
    print(f"  3. Added tagger 'test-user': taggers={data['taggers']}")

    # Step 3: Add an untagger
    data = cts_client.add_untagger(tag_id, "other-user")
    assert "test-user" in data["taggers"]
    print(f"  4. Added untagger 'other-user': untaggers={data['untaggers']}")

    # Step 4: Add another tagger
    data = cts_client.add_tagger(tag_id, "another-user")
    assert set(data["taggers"]) == {"test-user", "another-user"}
    print(f"  5. Added tagger 'another-user': taggers={data['taggers']}")

    # Step 5: Remove a tagger
    data = cts_client.remove_tagger(tag_id, "test-user")
    assert "another-user" in data["taggers"]
    print(f"  6. Removed tagger 'test-user': taggers={data['taggers']}")

    # Step 6: Remove the untagger
    data = cts_client.remove_untagger(tag_id, "other-user")
    print(f"  7. Removed untagger 'other-user': untaggers={data['untaggers']}")

    # Step 7: Verify final state
    status, final_data = cts_client.http.get(f"/api/1/tags/{tag_id}")
    assert status == 200
    assert final_data["taggers"] == ["another-user"]
    assert final_data["untaggers"] == []
    print(
        f"  8. Final state - taggers: {final_data['taggers']}, untaggers: {final_data['untaggers']}"
    )
    print("  ✓ Tag creation and tagger/untagger management completed successfully")


def test_workflow_compose_import(cts_client):
    """Test importing a compose"""
    data = cts_client.import_compose(
        "IntegrationTest",
        "1.0",
        "20250101",
    )
    compose_id = data["payload"]["compose"]["id"]
    print(f"  Imported compose: {compose_id}")


def test_workflow_respin_increment(cts_client):
    """Test that respin numbers are automatically incremented for duplicate composes"""
    # Import first compose
    response1 = cts_client.import_compose(
        "RespinTest",
        "1.0",
        "20250102",
    )
    compose_id1 = response1["payload"]["compose"]["id"]
    respin1 = response1["payload"]["compose"]["respin"]
    print(f"  1. First compose: {compose_id1} (respin: {respin1})")

    # Import second compose with same release/date - respin should auto-increment
    response2 = cts_client.import_compose(
        "RespinTest",
        "1.0",
        "20250102",
    )
    compose_id2 = response2["payload"]["compose"]["id"]
    respin2 = response2["payload"]["compose"]["respin"]
    print(f"  2. Second compose: {compose_id2} (respin: {respin2})")

    # Import third compose - respin should increment again
    response3 = cts_client.import_compose(
        "RespinTest",
        "1.0",
        "20250102",
    )
    compose_id3 = response3["payload"]["compose"]["id"]
    respin3 = response3["payload"]["compose"]["respin"]
    print(f"  3. Third compose: {compose_id3} (respin: {respin3})")

    # Verify respin numbers are incremented
    assert (
        respin2 == respin1 + 1
    ), f"Second respin should be {respin1 + 1}, got {respin2}"
    assert (
        respin3 == respin2 + 1
    ), f"Third respin should be {respin2 + 1}, got {respin3}"

    # Verify compose IDs reflect the correct respin numbers
    assert f".t.{respin1}" in compose_id1
    assert f".t.{respin2}" in compose_id2
    assert f".t.{respin3}" in compose_id3

    print(f"  ✓ Respin auto-increment verified: {respin1} → {respin2} → {respin3}")


def test_workflow_full_lifecycle(cts_client):
    """Test complete workflow: create tag, import compose, tag it, untag it"""
    # Step 1: Create a tag
    tag_response = cts_client.create_tag(
        "workflow-test",
        "Tag for workflow testing",
        "https://example.com/docs/workflow",
    )
    tag_id = tag_response["id"]
    tag_name = tag_response["name"]
    print(f"  1. Created tag: {tag_name} (ID: {tag_id})")

    # Step 2: Import a compose
    compose_response = cts_client.import_compose(
        "WorkflowTest",
        "1.0",
        "20250101",
    )
    compose_id = compose_response["payload"]["compose"]["id"]
    print(f"  2. Imported compose: {compose_id}")

    # Verify compose has no tags initially
    status, compose_data = cts_client.http.get(f"/api/1/composes/{compose_id}")
    assert status == 200
    assert "tags" in compose_data
    initial_tags = compose_data.get("tags", [])
    print(f"  3. Initial tags: {initial_tags}")

    # Step 3: Tag the compose
    tag_result = cts_client.tag_compose(compose_id, tag_name)
    print(f"  4. Tagged compose with '{tag_name}': {tag_result.get('tags', [])}")

    # Step 4: Verify tag was applied
    status, compose_data = cts_client.http.get(f"/api/1/composes/{compose_id}")
    assert status == 200
    assert tag_name in compose_data.get("tags", [])
    print(f"  5. Verified tags: {compose_data.get('tags', [])}")

    # Step 5: Untag the compose
    untag_result = cts_client.untag_compose(compose_id, tag_name)
    print(f"  6. Untagged compose: {untag_result.get('tags', [])}")

    # Step 6: Verify tag was removed
    status, compose_data = cts_client.http.get(f"/api/1/composes/{compose_id}")
    assert status == 200
    assert tag_name not in compose_data.get("tags", [])
    print(f"  7. Final tags: {compose_data.get('tags', [])}")
    print("  ✓ Full workflow completed successfully")


# OIDC authentication tests
# These are skipped when AUTH_BACKEND is "noauth" or unset.


def test_auth_unauthenticated_write_returns_401(http_client):
    """Unauthenticated POST to a write endpoint must return 401 when openidc is active."""
    if not _is_oidc_backend():
        pytest.skip("OIDC auth tests require AUTH_BACKEND=openidc or oidc_or_kerberos")

    compose_info = _create_compose_info("AuthTest", "1.0", "20260101")
    status, data = http_client.post("/api/1/composes/", {"compose_info": compose_info})
    assert (
        status == 401
    ), f"Expected 401 for unauthenticated POST, got {status}. Response: {data}"
    # Confirm the unauthenticated path is indeed blocked (positive + negative check)
    assert status != 200, "Unauthenticated write must not succeed"


def test_auth_builder_can_post_compose(cts_auth_client):
    """Authenticated 'builder' user (in ALLOWED_BUILDERS) can POST a compose."""
    data = cts_auth_client.import_compose("AuthBuilderTest", "1.0", "20260101")
    compose_id = data["payload"]["compose"]["id"]
    assert compose_id, "Compose ID must be non-empty"


def test_auth_unauthorized_user_returns_403(auth_http_client_readonly):
    """Authenticated 'readonly' user (not in ALLOWED_BUILDERS) gets 403 on write endpoints."""
    compose_info = _create_compose_info("AuthReadonlyTest", "1.0", "20260101")
    status, data = auth_http_client_readonly.post(
        "/api/1/composes/", {"compose_info": compose_info}
    )
    assert (
        status == 403
    ), f"Expected 403 for readonly user POST, got {status}. Response: {data}"
    # Confirm write is actually blocked (not silently succeeding)
    assert status != 200, "Unauthorized user must not be able to write"


def test_auth_get_endpoints_accessible_without_token(http_client):
    """GET endpoints remain accessible without authentication (mod_auth_openidc pass-through)."""
    # Listing composes must work without a token
    status, data = http_client.get("/api/1/composes/")
    assert (
        status == 200
    ), f"Expected 200 for unauthenticated GET /api/1/composes/, got {status}"
    assert "items" in data, "GET response must contain 'items' key"

    # Listing tags must also work without a token
    status, data = http_client.get("/api/1/tags/")
    assert (
        status == 200
    ), f"Expected 200 for unauthenticated GET /api/1/tags/, got {status}"
    assert isinstance(data, dict), "GET /api/1/tags/ must return a dict"


# Kafka messaging helpers
# These helpers integrate Kafka assertions into existing workflow tests.
# Assertions are active only when KAFKA_URL is set; the tests run in either case.

_KAFKA_CONSUMER_TIMEOUT_MS = int(os.environ.get("KAFKA_CONSUMER_TIMEOUT_MS", 30000))

# Topics that CTS publishes to.
_CTS_KAFKA_TOPICS = [
    "cts.compose-created",
    "cts.compose-tagged",
    "cts.compose-untagged",
]


def _make_json_deserializer():
    """Return a ``kafka.serializer.Deserializer`` subclass for JSON messages.

    We import ``kafka.serializer.Deserializer`` lazily (inside the function) so
    that the rest of the test module can be imported even when ``kafka-python``
    is not installed.  Subclassing the ABC causes ``isinstance`` to return True
    in ``KafkaConsumer.__init__``, which prevents the consumer from wrapping our
    class in ``DeserializeWrapper`` — the wrapper treats the deserializer as a
    plain callable and breaks when it is not one.
    """
    from kafka.serializer import Deserializer

    class _JsonDeserializer(Deserializer):
        def deserialize(self, topic, headers, data):
            return json.loads(data.decode("utf-8"))

        def close(self):
            pass

    return _JsonDeserializer()


@pytest.fixture(scope="module")
def kafka_consumer():
    """Return a long-lived KafkaConsumer subscribed to all CTS topics.

    The consumer is positioned at the *current* end of each topic when the
    module starts, so it only sees messages produced during this test run.  It
    acts as a cursor: each call to ``_consume_one`` advances the position
    forward, making offset tracking unnecessary.

    Returns ``None`` when ``KAFKA_URL`` is not set.  All Kafka-aware helpers
    and tests check for ``None`` and skip their assertions accordingly, so the
    full test suite runs in environments without a Kafka broker.
    """
    kafka_url = os.environ.get("KAFKA_URL")
    if not kafka_url:
        yield None
        return

    from kafka import KafkaConsumer, TopicPartition
    from kafka.errors import KafkaConnectionError, KafkaTimeoutError

    try:
        consumer = KafkaConsumer(
            bootstrap_servers=kafka_url,
            # No group_id: we use manual partition assignment, so the
            # group-coordinator protocol is not needed.
            group_id=None,
            value_deserializer=_make_json_deserializer(),
            request_timeout_ms=10000,
        )
    except (KafkaTimeoutError, KafkaConnectionError) as exc:
        pytest.fail(f"Cannot connect to Kafka broker at {kafka_url}: {exc}")
        return

    from kafka.errors import UnknownTopicOrPartitionError

    # Assign all topic partitions and seek to the current end so we only
    # see messages produced during this test run.
    partitions = [TopicPartition(t, 0) for t in _CTS_KAFKA_TOPICS]
    consumer.assign(partitions)
    for tp in partitions:
        try:
            consumer.seek_to_end(tp)
        except (UnknownTopicOrPartitionError, KafkaTimeoutError):
            # Topic may not exist yet (no messages published); seek to 0 so
            # that the first message on the topic is visible.
            consumer.seek(tp, 0)

    yield consumer
    consumer.close()


@pytest.fixture(autouse=True)
def _kafka_drain_check(kafka_consumer, request):
    """After each test, assert that no Kafka messages were left unconsumed.

    Any message on a CTS topic that was not explicitly consumed by the test is
    a sign of a bug (e.g. the application sent a duplicate or unexpected
    message, or the test forgot to consume a message it produced).  The fixture
    fails the test in that case so problems are caught immediately.
    """
    yield
    if kafka_consumer is None:
        return
    from kafka.errors import KafkaConnectionError

    stale = []
    try:
        records = kafka_consumer.poll(timeout_ms=500, max_records=10)
    except KafkaConnectionError:
        records = {}
    for recs in records.values():
        for rec in recs:
            stale.append((rec.topic, rec.offset, rec.value))
    if stale:
        details = "\n".join(
            f"  topic={t!r} offset={o} value={v!r}" for t, o, v in stale
        )
        pytest.fail(
            f"Unconsumed Kafka messages found after test {request.node.name!r}:\n"
            + details
        )


def _assert_compose_message(kafka_consumer, topic, event_name, compose_id):
    """Consume one message and assert it matches the expected event and compose.

    When *kafka_consumer* is ``None`` (no Kafka broker configured), this
    function returns immediately without making any assertions.
    """
    if kafka_consumer is None:
        return
    msg = _consume_one(kafka_consumer, topic)
    assert (
        msg.get("event") == event_name
    ), f"Expected event={event_name!r}, got event={msg.get('event')!r}"
    assert msg.get("compose") is not None, f"Message missing 'compose' key: {msg}"
    compose_info_data = msg["compose"].get("compose_info", {})
    assert compose_id in str(
        compose_info_data
    ), f"Message compose_info does not reference compose {compose_id}: {msg}"


def _consume_one(consumer, topic, timeout_ms=None):
    """Consume and return the next message on *topic* from *consumer*.

    The consumer is long-lived and acts as a cursor, so successive calls to
    this function return successive messages in order without any offset
    bookkeeping.

    Raises ``AssertionError`` if a message arrives on any topic other than
    *topic* (unexpected message), or if no message arrives within *timeout_ms*
    (default: ``_KAFKA_CONSUMER_TIMEOUT_MS``).
    """
    from kafka.errors import KafkaConnectionError

    if timeout_ms is None:
        timeout_ms = _KAFKA_CONSUMER_TIMEOUT_MS

    deadline_ms = timeout_ms
    while deadline_ms > 0:
        poll_ms = min(deadline_ms, 500)
        try:
            records = consumer.poll(timeout_ms=poll_ms, max_records=1)
        except KafkaConnectionError as exc:
            raise AssertionError(
                f"Kafka broker disconnected while consuming topic '{topic}': {exc}"
            ) from exc
        for tp_key, recs in records.items():
            for rec in recs:
                if tp_key.topic != topic:
                    raise AssertionError(
                        f"Expected message on topic '{topic}' but received one on '{tp_key.topic}' (offset={rec.offset}, value={rec.value!r})"
                    )
                return rec.value
        deadline_ms -= poll_ms
    raise AssertionError(
        f"No message received on Kafka topic '{topic}' within {timeout_ms} ms"
    )


# Standalone Kafka integration tests
# These tests are explicitly skipped when KAFKA_URL is not set.
# They verify that CTS publishes the correct Kafka message for each
# compose lifecycle event.


def test_kafka_compose_created(cts_client):
    """Verify that importing a compose publishes a compose-created Kafka message.

    Skipped when KAFKA_URL is not set (no Kafka broker available).
    """
    if cts_client.kafka is None:
        pytest.skip("requires KAFKA_URL")

    data = cts_client.import_compose(
        "KafkaCreatedTest",
        "1.0",
        "20260101",
    )
    compose_id = data["payload"]["compose"]["id"]
    assert compose_id, "Compose ID must be non-empty"


def test_kafka_compose_tagged(cts_client):
    """Verify that tagging a compose publishes a compose-tagged Kafka message.

    Skipped when KAFKA_URL is not set (no Kafka broker available).
    """
    if cts_client.kafka is None:
        pytest.skip("requires KAFKA_URL")

    # Create a tag, then import a compose and apply the tag.
    tag_data = cts_client.create_tag(
        "kafka-tagged-test",
        "Tag for Kafka tagged test",
        "https://example.com/docs/kafka-tagged",
    )
    tag_name = tag_data["name"]

    compose_data = cts_client.import_compose(
        "KafkaTaggedTest",
        "1.0",
        "20260102",
    )
    compose_id = compose_data["payload"]["compose"]["id"]

    cts_client.tag_compose(compose_id, tag_name)


def test_kafka_compose_untagged(cts_client):
    """Verify that untagging a compose publishes a compose-untagged Kafka message.

    Skipped when KAFKA_URL is not set (no Kafka broker available).
    """
    if cts_client.kafka is None:
        pytest.skip("requires KAFKA_URL")

    # Create a tag, import a compose, tag it, then untag it.
    tag_data = cts_client.create_tag(
        "kafka-untagged-test",
        "Tag for Kafka untagged test",
        "https://example.com/docs/kafka-untagged",
    )
    tag_name = tag_data["name"]

    compose_data = cts_client.import_compose(
        "KafkaUntaggedTest",
        "1.0",
        "20260103",
    )
    compose_id = compose_data["payload"]["compose"]["id"]

    cts_client.tag_compose(compose_id, tag_name)
    cts_client.untag_compose(compose_id, tag_name)
