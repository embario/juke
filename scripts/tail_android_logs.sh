#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
API_LEVEL="${1:-36}"
AVD_NAME="jukeApi${API_LEVEL}"
LOG_DIR="${REPO_ROOT}/.android-emulator"
LOG_FILE="${LOG_DIR}/${AVD_NAME}.log"

mkdir -p "${LOG_DIR}"
touch "${LOG_FILE}"

cat <<EOF
Tailing emulator log at ${LOG_FILE}
Press Ctrl-C to stop. Use scripts/build_and_run_android.sh to trigger a build/run.
EOF

cleanup() {
    if [[ -n "${TAIL_PID:-}" ]]; then
        kill "${TAIL_PID}" 2>/dev/null || true
    fi
    if [[ -n "${LOGCAT_PID:-}" ]]; then
        kill "${LOGCAT_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT

tail -n 50 -F "${LOG_FILE}" &
TAIL_PID=$!

adb logcat -v color fm.juke.mobile:D AndroidRuntime:E *:S &
LOGCAT_PID=$!

wait "${TAIL_PID}"
wait "${LOGCAT_PID}" || true
