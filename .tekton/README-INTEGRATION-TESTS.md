# CTS Integration Tests for Konflux CI

## Overview

The integration test scenario validates that the built CTS container image
works correctly by provisioning an ephemeral environment and deploying the
service with a real PostgreSQL database.

## Files

### Integration Test Scenario

- **`cts-integration-test.yaml`** - IntegrationTestScenario CRD that defines
  when and how tests run
  - Runs automatically after successful builds
  - References the test pipeline
  - Marks failed builds if tests fail

### Test Pipelines

- **`integration-test-eaas.yaml`** - EaaS-based integration test
  - Uses Konflux EaaS (Environment as a Service) to provision ephemeral namespace
  - Deploys real PostgreSQL database
  - Deploys CTS service with the built image
  - Tests actual API functionality
  - Automatically cleans up when pipeline completes
  - Full integration testing with proper Kubernetes resources

### Test Scripts

- **`../tests/test_integration_api.py`** - Integration tests using pytest
  - Uses pytest fixtures for clean test setup
  - Makes direct HTTP requests to CTS API
  - Run with: `CTS_URL=http://localhost:5005 pytest tests/test_integration_api.py -v`
  - In CI, runs in a pod deployed to the same namespace as CTS
  - Tests all major API endpoints and workflows
  - Edit this file to add or modify integration tests

## What Gets Tested

The integration tests validate:

- ✅ **Service Startup** - Container starts without errors
- ✅ **Database Connectivity** - Migrations run successfully
- ✅ **API Endpoints** - All major endpoints respond correctly:
  - `GET /api/1/` - API root
  - `GET /api/1/about/` - Version information
  - `GET /api/1/composes/` - Compose listing
  - `GET /api/1/openapi.json` - OpenAPI specification
- ✅ **Error Handling** - 404 responses for invalid endpoints
- ✅ **Pagination** - Query parameters work correctly

## How It Works

### In Konflux CI

1. Code is pushed to the repository or PR is created
2. Tekton build pipeline builds the container image
3. **IntegrationTestScenario** automatically triggers
4. Test pipeline deploys and validates the image
5. Results are reported back to the PR/commit

### Pipeline Execution Flow (EaaS approach)

```
┌─────────────────────────────┐
│ 1. Parse Snapshot           │  Extract image URL, git URL, git revision
└─────────────┬───────────────┘
              │
┌─────────────▼───────────────┐
│ 2. Provision Environment    │  Create ephemeral namespace via EaaS
│                             │  Returns kubeconfig secret
└─────────────┬───────────────┘
              │
┌─────────────▼───────────────┐
│ 3. Deploy PostgreSQL        │  Create Deployment & Service in ephemeral ns
└─────────────┬───────────────┘
              │
┌─────────────▼───────────────┐
│ 4. Deploy CTS Service       │  Create Deployment & Service in ephemeral ns
└─────────────┬───────────────┘
              │
┌─────────────▼───────────────┐
│ 5. Run Integration Tests    │  Create test runner pod in ephemeral ns
│                             │  Install pytest, clone repo
│                             │  Run tests with direct HTTP to CTS service
└─────────────┬───────────────┘
              │
┌─────────────▼───────────────┐
│ 6. Automatic Cleanup        │  Ephemeral namespace deleted by EaaS
│                             │  (includes test runner, CTS, and database)
└─────────────────────────────┘
```

## Running Tests Locally

```bash
# Point to your deployment
CTS_URL=https://cts.example.com pytest tests/test_integration_api.py -v
```


## Customizing Tests

### Adding New Test Cases

Edit `tests/test_integration_api.py` and add new test functions:

```python
def test_my_new_feature(http_client):
    """Test my new API endpoint"""
    status, data = http_client.get('/api/1/my-endpoint/')
    assert status == 200
    assert 'expected_field' in data
```

That's it! Pytest automatically discovers and runs all `test_*` functions.
No need to manually register tests or track results.

### Modifying the Test Environment

Edit `.tekton/integration-test-eaas.yaml` to change:

- Database configuration (in the `deploy-database` task's Deployment spec)
- CTS environment variables (in the `deploy-cts` task's Deployment spec)
- Test execution logic (in the `run-tests` task's Python script)


## Related Documentation

- [Konflux Integration Tests](https://konflux-ci.dev/docs/how-tos/testing/integration/)
- [Tekton Pipelines](https://tekton.dev/docs/pipelines/)
