#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
    return 0
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
