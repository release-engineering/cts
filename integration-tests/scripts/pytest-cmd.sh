#!/usr/bin/env bash
# run_pytest REPO_PATH DEX_CA_PATH
# Runs the CTS integration test suite with the standard environment variables.
# Intended to be sourced on the host and then the function definition passed
# into a test runner pod via "$(declare -f run_pytest)" inside a bash -c block.
run_pytest() {
    local repo_path="$1"
    local dex_ca_path="$2"
    cd "$repo_path"
    REQUESTS_CA_BUNDLE="$dex_ca_path" \
    CTS_URL=http://cts:8080 \
    AUTH_BACKEND=oidc_or_kerberos \
    DEX_URL=https://dex:5556 \
    KAFKA_URL=kafka:9092 \
        python3 -m pytest tests/test_integration_api.py -v -s -o addopts=
}
