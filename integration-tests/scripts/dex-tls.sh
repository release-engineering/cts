#!/usr/bin/env bash
# generate_dex_tls OUTDIR [KUBECTL]
# Generates a self-signed CA and Dex server TLS certificate, then creates
# the dex-tls and dex-ca Kubernetes secrets.
# OUTDIR must exist. Caller is responsible for deleting it afterwards.
# KUBECTL defaults to "kubectl"; pass e.g. "kubectl -n mynamespace" for
# namespace-scoped operation without a namespace-configured kubeconfig.
generate_dex_tls() {
    local outdir="$1"
    local kubectl_cmd="${2:-kubectl}"

    openssl genrsa -out "$outdir/ca.key" 4096 2>/dev/null
    openssl req -x509 -new -nodes -key "$outdir/ca.key" \
        -sha256 -days 365 -subj "/CN=dex-test-ca" \
        -out "$outdir/ca.crt" 2>/dev/null

    openssl genrsa -out "$outdir/dex.key" 4096 2>/dev/null
    openssl req -new -key "$outdir/dex.key" \
        -subj "/CN=dex" \
        -out "$outdir/dex.csr" 2>/dev/null

    # Use printf to avoid heredoc indentation sensitivity
    printf '[SAN]\nsubjectAltName=DNS:dex\n' > "$outdir/dex.ext"

    openssl x509 -req -in "$outdir/dex.csr" \
        -CA "$outdir/ca.crt" -CAkey "$outdir/ca.key" -CAcreateserial \
        -out "$outdir/dex.crt" -days 365 -sha256 \
        -extfile "$outdir/dex.ext" -extensions SAN 2>/dev/null

    $kubectl_cmd create secret generic dex-tls \
        --from-file=tls.crt="$outdir/dex.crt" \
        --from-file=tls.key="$outdir/dex.key"

    $kubectl_cmd create secret generic dex-ca \
        --from-file=ca.crt="$outdir/ca.crt"
}
