#!/usr/bin/env bash
# setup_kubeconfig SECRET_NAME
# Retrieves a kubeconfig from a Kubernetes secret and exports KUBECONFIG.
setup_kubeconfig() {
    local secret_name="$1"
    KUBECONFIG=/tmp/kubeconfig
    kubectl get secret "$secret_name" -o jsonpath='{.data.kubeconfig}' | base64 -d > "$KUBECONFIG"
    export KUBECONFIG
}
