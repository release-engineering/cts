#!/usr/bin/env bash
# Functions to deploy individual infrastructure services and wait for readiness.
# Each function accepts an optional KUBECTL argument (default: "kubectl") so that
# callers without a namespace-scoped kubeconfig can pass "kubectl -n NAMESPACE".
# Note: deploy_openldap's ldap-data ConfigMap creation is not idempotent;
# it is expected to run once per fresh namespace.

# deploy_postgres MANIFESTS_DIR [KUBECTL]
deploy_postgres() {
    local manifests="$1"
    local kubectl_cmd="${2:-kubectl}"

    echo "=========================================="
    echo "Deploying PostgreSQL"
    echo "=========================================="

    $kubectl_cmd apply -f "${manifests}/postgres.yaml"

    echo "Waiting for database to be ready..."
    if ! $kubectl_cmd wait --for=condition=available --timeout=180s deployment/cts-db; then
        echo "Database deployment failed! Debug info:"
        $kubectl_cmd describe deployment cts-db
        $kubectl_cmd describe pod -l app=cts-db
        $kubectl_cmd logs -l app=cts-db --tail=100 || true
        $kubectl_cmd get events --sort-by='.lastTimestamp'
        return 1
    fi
    echo "✓ Database is ready"
}

# deploy_openldap MANIFESTS_DIR LDAP_IMAGE DATA_DIR [KUBECTL]
deploy_openldap() {
    local manifests="$1"
    local ldap_image="$2"
    local data_dir="$3"
    local kubectl_cmd="${4:-kubectl}"

    echo "=========================================="
    echo "Deploying LDAP Server"
    echo "=========================================="
    echo "Using LDAP server image: $ldap_image"

    echo "Creating ldap-data ConfigMap..."
    $kubectl_cmd create configmap ldap-data \
        --from-file=groups.ldif="${data_dir}/groups.ldif"

    sed "s|\${LDAP_IMAGE}|${ldap_image}|g" "${manifests}/openldap.yaml" \
        | $kubectl_cmd apply -f -

    echo "Waiting for LDAP server to be ready..."
    if ! $kubectl_cmd wait --for=condition=available --timeout=180s deployment/openldap; then
        echo "LDAP deployment failed! Debug info:"
        $kubectl_cmd describe deployment openldap
        $kubectl_cmd describe pod -l app=openldap
        $kubectl_cmd logs -l app=openldap --tail=50 || true
        return 1
    fi
    echo "✓ LDAP server is ready"
}

# deploy_dex_manifests MANIFESTS_DIR [KUBECTL]
deploy_dex_manifests() {
    local manifests="$1"
    local kubectl_cmd="${2:-kubectl}"

    echo "=========================================="
    echo "Deploying Dex OIDC Provider"
    echo "=========================================="

    $kubectl_cmd apply -f "${manifests}/dex-config.yaml"
    $kubectl_cmd apply -f "${manifests}/dex.yaml"

    echo "Waiting for Dex to be ready..."
    if ! $kubectl_cmd wait --for=condition=available --timeout=180s deployment/dex; then
        echo "Dex deployment failed! Debug info:"
        $kubectl_cmd describe deployment dex
        $kubectl_cmd describe pod -l app=dex
        $kubectl_cmd logs -l app=dex --tail=50 || true
        return 1
    fi
    echo "✓ Dex is ready"
}

# deploy_kafka MANIFESTS_DIR [KUBECTL]
deploy_kafka() {
    local manifests="$1"
    local kubectl_cmd="${2:-kubectl}"

    echo "=========================================="
    echo "Deploying Kafka"
    echo "=========================================="

    $kubectl_cmd apply -f "${manifests}/kafka.yaml"

    echo "Waiting for Kafka to be ready..."
    if ! $kubectl_cmd wait --for=condition=available --timeout=300s deployment/kafka; then
        echo "Kafka deployment failed! Debug info:"
        $kubectl_cmd describe deployment kafka
        $kubectl_cmd describe pod -l app=kafka
        $kubectl_cmd logs -l app=kafka --tail=50 || true
        return 1
    fi
    echo "✓ Kafka is ready"
}
