#!/usr/bin/env bash
# deploy_cts MANIFESTS_DIR IMAGE [KUBECTL]
# Deploys the CTS service and waits for it to become available.
# KUBECTL defaults to "kubectl"; pass e.g. "kubectl -n NAMESPACE" for
# namespace-scoped operation without a namespace-configured kubeconfig.
deploy_cts() {
    local manifests="$1"
    local image="$2"
    local kubectl_cmd="${3:-kubectl}"

    echo "=========================================="
    echo "Deploying CTS Service"
    echo "=========================================="
    echo "Image: $image"

    $kubectl_cmd create configmap cts-config \
        --from-file=config.py="${manifests}/config.py" \
        --from-file=httpd.conf="${manifests}/httpd.conf" \
        --dry-run=client -o yaml | $kubectl_cmd apply -f -

    sed "s|\${IMAGE}|${image}|g" "${manifests}/cts.yaml" \
        | $kubectl_cmd apply -f -

    echo "Waiting for CTS service to be ready..."
    if ! $kubectl_cmd wait --for=condition=available --timeout=300s deployment/cts; then
        echo "CTS deployment failed! Debug info:"
        $kubectl_cmd describe deployment cts
        $kubectl_cmd describe pod -l app=cts
        $kubectl_cmd logs -l app=cts --all-containers --tail=100 || true
        $kubectl_cmd get events --sort-by='.lastTimestamp' | tail -30
        return 1
    fi
    echo "✓ CTS service is ready"
}
