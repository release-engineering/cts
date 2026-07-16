#!/bin/bash
#
# Run the CTS integration test pipeline locally using kind.
#
# This script replicates what .tekton/integration-test-eaas.yaml does
# on Konflux, but uses a local kind cluster instead of an ephemeral
# EaaS namespace. Tests run inside the cluster (in a pod) to match the
# CI pipeline behavior and avoid port-forwarding issues.
#
# Like the CI pipeline, each run gets a fresh namespace so there is no
# stale state from previous runs.
#
# Prerequisites: kind, kubectl, podman (or docker), openssl
#
# Usage:
#   ./integration-tests/run-local.sh                 # build images and run tests
#   ./integration-tests/run-local.sh --skip-build    # reuse existing images
#   ./integration-tests/run-local.sh --keep-cluster  # don't delete cluster on exit
#   ./integration-tests/run-local.sh --no-tests      # deploy only, skip tests
#
# Environment variables:
#   CTS_IMAGE        - pre-built CTS image to use (skips CTS image build)
#   LDAP_IMAGE       - pre-built LDAP server image to use (skips LDAP build)
#   KIND_CLUSTER     - cluster name (default: cts-integration)
#   CONTAINER_ENGINE - podman or docker (auto-detected)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFESTS="$REPO_ROOT/integration-tests/manifests"
DATA="$REPO_ROOT/integration-tests/data"

KIND_CLUSTER="${KIND_CLUSTER:-cts-integration}"
NAMESPACE="cts-test-$(date +%s)"
SKIP_BUILD=false
KEEP_CLUSTER=false
NO_TESTS=false

for arg in "$@"; do
    case "$arg" in
        --skip-build) SKIP_BUILD=true ;;
        --keep-cluster) KEEP_CLUSTER=true ;;
        --no-tests) NO_TESTS=true ;;
        --help|-h)
            sed -n '2,/^$/s/^# \?//p' "$0"
            exit 0
            ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Detect container engine
# ---------------------------------------------------------------------------
if [ -n "${CONTAINER_ENGINE:-}" ]; then
    :
elif command -v podman &>/dev/null; then
    CONTAINER_ENGINE=podman
elif command -v docker &>/dev/null; then
    CONTAINER_ENGINE=docker
else
    echo "Error: neither podman nor docker found" >&2
    exit 1
fi
echo "Container engine: $CONTAINER_ENGINE"

# When using podman, kind needs this env var
if [ "$CONTAINER_ENGINE" = "podman" ]; then
    export KIND_EXPERIMENTAL_PROVIDER=podman
fi

# ---------------------------------------------------------------------------
# Cleanup handler
# ---------------------------------------------------------------------------
_TMPDIR=""
cleanup() {
    [ -n "$_TMPDIR" ] && rm -rf "$_TMPDIR"
    if [ "$KEEP_CLUSTER" = false ]; then
        echo ""
        echo "Cleaning up kind cluster '$KIND_CLUSTER'..."
        kind delete cluster --name "$KIND_CLUSTER" 2>/dev/null || true
    else
        echo ""
        echo "Cleaning up namespace '$NAMESPACE'..."
        kubectl delete namespace "$NAMESPACE" --ignore-not-found=true --wait=false 2>/dev/null || true
        echo "Cluster '$KIND_CLUSTER' kept. Delete later with:"
        echo "  kind delete cluster --name $KIND_CLUSTER"
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Build container images
# ---------------------------------------------------------------------------
CTS_IMAGE="${CTS_IMAGE:-localhost/cts:integration-test}"
LDAP_IMAGE="${LDAP_IMAGE:-localhost/cts-ldap-server:integration-test}"

if [ "$SKIP_BUILD" = false ]; then
    echo "=========================================="
    echo "Building CTS image"
    echo "=========================================="
    $CONTAINER_ENGINE build -t "$CTS_IMAGE" \
        --build-arg short_commit="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo local)" \
        "$REPO_ROOT"

    echo ""
    echo "=========================================="
    echo "Building LDAP server image"
    echo "=========================================="
    $CONTAINER_ENGINE build -t "$LDAP_IMAGE" \
        -f "$REPO_ROOT/integration-tests/images/ldap-server/Containerfile" \
        "$REPO_ROOT/integration-tests/images/ldap-server"
fi

# ---------------------------------------------------------------------------
# Create kind cluster (reused across runs)
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "Creating kind cluster '$KIND_CLUSTER'"
echo "=========================================="
if kind get clusters 2>/dev/null | grep -qx "$KIND_CLUSTER"; then
    echo "Cluster '$KIND_CLUSTER' already exists, reusing it."
else
    kind create cluster --name "$KIND_CLUSTER" --wait 60s
fi

# ---------------------------------------------------------------------------
# Load images into kind
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "Loading images into kind"
echo "=========================================="
kind load docker-image "$CTS_IMAGE" --name "$KIND_CLUSTER"
kind load docker-image "$LDAP_IMAGE" --name "$KIND_CLUSTER"

# ---------------------------------------------------------------------------
# Create a fresh namespace (mirrors the ephemeral EaaS namespace in CI)
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "Creating namespace '$NAMESPACE'"
echo "=========================================="
kubectl create namespace "$NAMESPACE"

# All subsequent kubectl calls target the test namespace.  Use a wrapper
# function instead of "kubectl config set-context" to avoid mutating the
# user's kubeconfig.
kube() { kubectl -n "$NAMESPACE" "$@"; }

# ---------------------------------------------------------------------------
# Deploy PostgreSQL
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "Deploying PostgreSQL"
echo "=========================================="
kube apply -f "$MANIFESTS/postgres.yaml"

# ---------------------------------------------------------------------------
# Deploy OpenLDAP
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "Deploying OpenLDAP (LDAP server)"
echo "=========================================="
kube create configmap ldap-data \
    --from-file=groups.ldif="$DATA/groups.ldif"

sed "s|\${LDAP_IMAGE}|${LDAP_IMAGE}|g" "$MANIFESTS/openldap.yaml" \
    | kube apply -f -

# ---------------------------------------------------------------------------
# Deploy Dex (OIDC provider) with self-signed TLS
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "Generating Dex TLS certificates"
echo "=========================================="
_TMPDIR=$(mktemp -d)

openssl genrsa -out "$_TMPDIR/ca.key" 4096 2>/dev/null
openssl req -x509 -new -nodes -key "$_TMPDIR/ca.key" \
    -sha256 -days 365 -subj "/CN=dex-test-ca" \
    -out "$_TMPDIR/ca.crt" 2>/dev/null

openssl genrsa -out "$_TMPDIR/dex.key" 4096 2>/dev/null
openssl req -new -key "$_TMPDIR/dex.key" \
    -subj "/CN=dex" \
    -out "$_TMPDIR/dex.csr" 2>/dev/null

cat > "$_TMPDIR/dex.ext" <<'EOF'
[SAN]
subjectAltName=DNS:dex
EOF
openssl x509 -req -in "$_TMPDIR/dex.csr" \
    -CA "$_TMPDIR/ca.crt" -CAkey "$_TMPDIR/ca.key" -CAcreateserial \
    -out "$_TMPDIR/dex.crt" -days 365 -sha256 \
    -extfile "$_TMPDIR/dex.ext" -extensions SAN 2>/dev/null

kube create secret generic dex-tls \
    --from-file=tls.crt="$_TMPDIR/dex.crt" \
    --from-file=tls.key="$_TMPDIR/dex.key"

kube create secret generic dex-ca \
    --from-file=ca.crt="$_TMPDIR/ca.crt"

echo "Deploying Dex..."
kube apply -f "$MANIFESTS/dex-config.yaml"
kube apply -f "$MANIFESTS/dex.yaml"

# ---------------------------------------------------------------------------
# Deploy Kafka
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "Deploying Kafka"
echo "=========================================="
kube apply -f "$MANIFESTS/kafka.yaml"

# ---------------------------------------------------------------------------
# Wait for infrastructure services
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "Waiting for infrastructure services..."
echo "=========================================="
kube wait --for=condition=available --timeout=300s \
    deployment/cts-db \
    deployment/openldap \
    deployment/dex \
    deployment/kafka

# ---------------------------------------------------------------------------
# Deploy CTS
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "Deploying CTS"
echo "=========================================="
kube create configmap cts-config \
    --from-file=config.py="$MANIFESTS/config.py" \
    --from-file=httpd.conf="$MANIFESTS/httpd.conf"

sed "s|\${IMAGE}|${CTS_IMAGE}|g" "$MANIFESTS/cts.yaml" \
    | kube apply -f -

echo "Waiting for CTS to be ready (includes DB migration init container)..."
if ! kube wait --for=condition=available --timeout=300s deployment/cts; then
    echo ""
    echo "CTS deployment failed! Debug info:"
    kube describe deployment cts
    kube describe pod -l app=cts
    echo "--- CTS logs ---"
    kube logs -l app=cts --all-containers --tail=100 || true
    echo "--- Events ---"
    kube get events --sort-by='.lastTimestamp' | tail -30
    exit 1
fi
echo "CTS is ready."

if [ "$NO_TESTS" = true ]; then
    echo ""
    echo "=========================================="
    echo "Deployment complete (--no-tests). Services:"
    echo "=========================================="
    echo "  kubectl -n $NAMESPACE port-forward svc/cts 8080:8080"
    echo "  Then: CTS_URL=http://localhost:8080 pytest tests/test_integration_api.py -v"
    echo ""
    echo "To tear down: kind delete cluster --name $KIND_CLUSTER"
    # The EXIT trap checks KEEP_CLUSTER: when true it deletes only the
    # namespace (preserving the cluster); when false it deletes the whole
    # cluster.  Setting it here keeps the deployment running for manual use.
    KEEP_CLUSTER=true
    exit 0
fi

# ---------------------------------------------------------------------------
# Run integration tests inside the cluster
#
# We run tests from inside a pod to match the CI pipeline.  This avoids
# port-forwarding problems (Kafka advertised listeners resolve only inside
# the cluster, and the Dex TLS cert has SAN=DNS:dex only).
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "Running integration tests"
echo "=========================================="

TEST_RUNNER_IMAGE="docker.io/library/python:3.12-slim"

# Pre-pull the image into kind so the pod starts quickly
kind load docker-image "$TEST_RUNNER_IMAGE" --name "$KIND_CLUSTER" 2>/dev/null || true

kube run cts-test-runner \
    --image="$TEST_RUNNER_IMAGE" \
    --restart=Never \
    --command -- sleep 3600

echo "Waiting for test runner pod..."
kube wait --for=condition=Ready pod/cts-test-runner --timeout=120s

# Copy the repository into the pod (excluding bulky build artifacts)
echo "Copying repository into test runner pod..."
kube exec cts-test-runner -- mkdir -p /tmp/cts-repo
# Use UID 0 and do not preserve host ownership for Podman
tar -C "$REPO_ROOT" \
--owner=0 --group=0 \
    --exclude=.git --exclude=.tox --exclude=__pycache__ \
    --exclude='*.egg-info' --exclude=.venv --exclude=venv \
    --exclude=docs/_build --exclude=.pytest_cache \
    -cf - . \
    | kube exec -i cts-test-runner -- tar -xf - -C /tmp/cts-repo

# Copy the Dex CA cert into the pod
kubectl cp "$_TMPDIR/ca.crt" "$NAMESPACE/cts-test-runner:/tmp/dex-ca.crt"

echo ""
echo "Installing test dependencies and running pytest..."
echo ""

# Run the tests
set +e
kube exec cts-test-runner -- bash -c "
    set -ex
    export HOME=/tmp

    echo 'Installing test dependencies...'
    pip install --quiet pytest requests kafka-python

    echo ''
    echo 'Running integration tests...'
    cd /tmp/cts-repo
    REQUESTS_CA_BUNDLE=/tmp/dex-ca.crt \
    CTS_URL=http://cts:8080 \
    AUTH_BACKEND=oidc_or_kerberos \
    DEX_URL=https://dex:5556 \
    KAFKA_URL=kafka:9092 \
        python3 -m pytest tests/test_integration_api.py -v -s -o addopts=
"
TEST_RESULT=$?
set -e

if [ $TEST_RESULT -eq 0 ]; then
    echo ""
    echo "All integration tests passed!"
else
    echo ""
    echo "Integration tests FAILED (exit code $TEST_RESULT)"
    echo ""
    echo "--- CTS logs ---"
    kube logs -l app=cts --tail=50 || true
    exit $TEST_RESULT
fi
