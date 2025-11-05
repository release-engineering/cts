"""
Integration tests for CTS API endpoints.

Run with pytest in one of two modes:

1. Direct HTTP mode (local testing):
   CTS_URL=http://localhost:5005 pytest tests/test_integration_api.py -v

2. Kubectl exec mode (CI testing):
   KUBECTL_POD=cts-abc123 pytest tests/test_integration_api.py -v

   Uses kubectl exec to run curl inside the CTS pod. URLs are properly quoted
   to handle special characters like & in query parameters.
"""

import json
import os
import subprocess
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

import pytest


class HTTPClient:
    """HTTP client that works in both direct and kubectl exec modes"""

    def __init__(self, base_url=None, kubectl_pod=None):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.kubectl_pod = kubectl_pod

    def _request(self, method, path, json_data=None):
        """Make HTTP request with specified method"""
        if self.kubectl_pod:
            # Kubectl exec mode - use curl
            # Important: Quote the URL to prevent shell interpretation of & and other special chars
            url = f"http://localhost:5005{path}"
            if json_data:
                json_str = json.dumps(json_data).replace("'", "'\\''")
                cmd = f"curl -s -w '\\n%{{http_code}}' -X {method} -H 'Content-Type: application/json' -d '{json_str}' '{url}'"
            else:
                cmd = f"curl -s -w '\\n%{{http_code}}' -X {method} '{url}'"

            result = subprocess.run(
                ["kubectl", "exec", "-i", self.kubectl_pod, "--", "sh", "-c", cmd],
                capture_output=True,
                text=True,
            )

            # Parse output: last line is status code, rest is body
            lines = result.stdout.rsplit("\n", 1)
            if len(lines) == 2:
                body, status_code = lines
                try:
                    status = int(status_code)
                except ValueError:
                    body = result.stdout
                    status = 200 if result.returncode == 0 else 500
            else:
                body = result.stdout
                status = 200 if result.returncode == 0 else 500

            # Try to parse as JSON
            try:
                return status, json.loads(body) if body.strip() else {}
            except json.JSONDecodeError:
                return status, body
        else:
            # Direct HTTP mode
            url = f"{self.base_url}{path}"
            req = Request(url, method=method)
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
                except:
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


@pytest.fixture(scope="module")
def http_client():
    """HTTP client fixture that auto-detects mode from environment"""
    kubectl_pod = os.environ.get("KUBECTL_POD")
    base_url = os.environ.get("CTS_URL")

    if kubectl_pod:
        print(f"\nUsing kubectl exec mode (pod: {kubectl_pod})")
        return HTTPClient(kubectl_pod=kubectl_pod)
    elif base_url:
        print(f"\nUsing direct HTTP mode (URL: {base_url})")
        return HTTPClient(base_url=base_url)
    else:
        pytest.skip("Must set either CTS_URL or KUBECTL_POD environment variable")


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


# Helper functions for common test operations


def create_tag(http_client, name, description, documentation):
    """Create a tag and return the response data"""
    tag_data = {
        "name": name,
        "description": description,
        "documentation": documentation,
    }
    status, data = http_client.post("/api/1/tags/", tag_data)
    assert status == 200, f"Failed to create tag: {data}"
    assert isinstance(data, dict)
    assert data["name"] == name
    assert "id" in data
    return data


def import_compose(
    http_client, release_short, release_version, date, compose_type="test", respin=1
):
    """Import a compose and return the response data"""
    compose_info = _create_compose_info(
        release_short, release_version, date, compose_type, respin
    )
    status, data = http_client.post("/api/1/composes/", {"compose_info": compose_info})
    assert status == 200, f"Failed to import compose: {data}"
    assert isinstance(data, dict)
    assert "payload" in data
    assert "compose" in data["payload"]
    return data


def tag_compose(http_client, compose_id, tag_name):
    """Tag a compose and return the response data"""
    status, data = http_client.patch(
        f"/api/1/composes/{compose_id}", {"action": "tag", "tag": tag_name}
    )
    assert status == 200, f"Failed to tag compose: {data}"
    assert tag_name in data.get("tags", [])
    return data


def untag_compose(http_client, compose_id, tag_name):
    """Untag a compose and return the response data"""
    status, data = http_client.patch(
        f"/api/1/composes/{compose_id}", {"action": "untag", "tag": tag_name}
    )
    assert status == 200, f"Failed to untag compose: {data}"
    assert tag_name not in data.get("tags", [])
    return data


def _manage_tag_user(http_client, tag_id, action, username):
    """Internal helper to manage tag users (taggers/untaggers)"""
    status, data = http_client.patch(
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


def add_tagger(http_client, tag_id, username):
    """Add a tagger to a tag and return the response data"""
    return _manage_tag_user(http_client, tag_id, "add_tagger", username)


def remove_tagger(http_client, tag_id, username):
    """Remove a tagger from a tag and return the response data"""
    return _manage_tag_user(http_client, tag_id, "remove_tagger", username)


def add_untagger(http_client, tag_id, username):
    """Add an untagger to a tag and return the response data"""
    return _manage_tag_user(http_client, tag_id, "add_untagger", username)


def remove_untagger(http_client, tag_id, username):
    """Remove an untagger from a tag and return the response data"""
    return _manage_tag_user(http_client, tag_id, "remove_untagger", username)


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


def test_composes_pagination(http_client):
    """Test that pagination parameters work correctly"""
    # Import 3 test composes
    compose_ids = []
    for i in range(1, 4):
        response = import_compose(http_client, "PaginationTest", "1.0", f"2025010{i}")
        compose_ids.append(response["payload"]["compose"]["id"])

    print(f"  Imported {len(compose_ids)} composes for pagination test")

    # Test page 1 with per_page=2
    status, data = http_client.get("/api/1/composes/?page=1&per_page=2")
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
    status, data = http_client.get("/api/1/composes/?page=2&per_page=2")
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


def test_workflow_tag_creation(http_client):
    """Test creating a tag and managing taggers/untaggers"""
    # Step 1: Create a tag
    data = create_tag(
        http_client,
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
    data = add_tagger(http_client, tag_id, "test-user")
    print(f"  3. Added tagger 'test-user': taggers={data['taggers']}")

    # Step 3: Add an untagger
    data = add_untagger(http_client, tag_id, "other-user")
    assert "test-user" in data["taggers"]
    print(f"  4. Added untagger 'other-user': untaggers={data['untaggers']}")

    # Step 4: Add another tagger
    data = add_tagger(http_client, tag_id, "another-user")
    assert set(data["taggers"]) == {"test-user", "another-user"}
    print(f"  5. Added tagger 'another-user': taggers={data['taggers']}")

    # Step 5: Remove a tagger
    data = remove_tagger(http_client, tag_id, "test-user")
    assert "another-user" in data["taggers"]
    print(f"  6. Removed tagger 'test-user': taggers={data['taggers']}")

    # Step 6: Remove the untagger
    data = remove_untagger(http_client, tag_id, "other-user")
    print(f"  7. Removed untagger 'other-user': untaggers={data['untaggers']}")

    # Step 7: Verify final state
    status, final_data = http_client.get(f"/api/1/tags/{tag_id}")
    assert status == 200
    assert final_data["taggers"] == ["another-user"]
    assert final_data["untaggers"] == []
    print(
        f"  8. Final state - taggers: {final_data['taggers']}, untaggers: {final_data['untaggers']}"
    )
    print("  ✓ Tag creation and tagger/untagger management completed successfully")


def test_workflow_compose_import(http_client):
    """Test importing a compose"""
    data = import_compose(http_client, "IntegrationTest", "1.0", "20250101")
    compose_id = data["payload"]["compose"]["id"]
    print(f"  Imported compose: {compose_id}")


def test_workflow_respin_increment(http_client):
    """Test that respin numbers are automatically incremented for duplicate composes"""
    # Import first compose
    response1 = import_compose(http_client, "RespinTest", "1.0", "20250102")
    compose_id1 = response1["payload"]["compose"]["id"]
    respin1 = response1["payload"]["compose"]["respin"]
    print(f"  1. First compose: {compose_id1} (respin: {respin1})")

    # Import second compose with same release/date - respin should auto-increment
    response2 = import_compose(http_client, "RespinTest", "1.0", "20250102")
    compose_id2 = response2["payload"]["compose"]["id"]
    respin2 = response2["payload"]["compose"]["respin"]
    print(f"  2. Second compose: {compose_id2} (respin: {respin2})")

    # Import third compose - respin should increment again
    response3 = import_compose(http_client, "RespinTest", "1.0", "20250102")
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


def test_workflow_full_lifecycle(http_client):
    """Test complete workflow: create tag, import compose, tag it, untag it"""
    # Step 1: Create a tag
    tag_response = create_tag(
        http_client,
        "workflow-test",
        "Tag for workflow testing",
        "https://example.com/docs/workflow",
    )
    tag_id = tag_response["id"]
    tag_name = tag_response["name"]
    print(f"  1. Created tag: {tag_name} (ID: {tag_id})")

    # Step 2: Import a compose
    compose_response = import_compose(http_client, "WorkflowTest", "1.0", "20250101")
    compose_id = compose_response["payload"]["compose"]["id"]
    print(f"  2. Imported compose: {compose_id}")

    # Verify compose has no tags initially
    status, compose_data = http_client.get(f"/api/1/composes/{compose_id}")
    assert status == 200
    assert "tags" in compose_data
    initial_tags = compose_data.get("tags", [])
    print(f"  3. Initial tags: {initial_tags}")

    # Step 3: Tag the compose
    tag_result = tag_compose(http_client, compose_id, tag_name)
    print(f"  4. Tagged compose with '{tag_name}': {tag_result.get('tags', [])}")

    # Step 4: Verify tag was applied
    status, compose_data = http_client.get(f"/api/1/composes/{compose_id}")
    assert status == 200
    assert tag_name in compose_data.get("tags", [])
    print(f"  5. Verified tags: {compose_data.get('tags', [])}")

    # Step 5: Untag the compose
    untag_result = untag_compose(http_client, compose_id, tag_name)
    print(f"  6. Untagged compose: {untag_result.get('tags', [])}")

    # Step 6: Verify tag was removed
    status, compose_data = http_client.get(f"/api/1/composes/{compose_id}")
    assert status == 200
    assert tag_name not in compose_data.get("tags", [])
    print(f"  7. Final tags: {compose_data.get('tags', [])}")
    print("  ✓ Full workflow completed successfully")
