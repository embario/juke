#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IOS_ROOT="${REPO_ROOT}/mobile/ios"
ANDROID_ROOT="${REPO_ROOT}/mobile/android"
source "${SCRIPT_DIR}/load_env.sh"
ANDROID_PROJECT_NAME="${ANDROID_PROJECT_NAME:-juke}"
ANDROID_APP_DIR="${ANDROID_ROOT}/${ANDROID_PROJECT_NAME}"
DERIVED_DATA_PATH="${REPO_ROOT}/.derived-data"
LOGS_DIR="${REPO_ROOT}/logs"
SIM_TARGET_DEFAULT="iPhone 17 Pro"
SIM_TARGET="${SIM_TARGET:-${SIM_TARGET_DEFAULT}}"

usage() {
    cat <<EOF
Usage: $(basename "$0") [-s simulator] [--ios-only | --android-only]

Options:
  -s  Simulator name or UUID (default: ${SIM_TARGET_DEFAULT})
  --ios-only      Run only iOS tests
  --android-only  Run only Android tests
EOF
}

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command '$1'." >&2
        exit 1
    fi
}

run_ios=true
run_android=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        -s)
            SIM_TARGET="$2"
            shift 2
            ;;
        --ios-only)
            run_android=false
            shift
            ;;
        --android-only)
            run_ios=false
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

mkdir -p "${DERIVED_DATA_PATH}" "${LOGS_DIR}"

set -x

echo "Mobile test runner"
echo "  repo: ${REPO_ROOT}"
echo "  ios: ${run_ios} (sim: ${SIM_TARGET})"
echo "  android: ${run_android} (project: ${ANDROID_PROJECT_NAME})"
echo "  env file: ${ENV_FILE:-.env}"

run_ios_tests() {
    local project_root="$1"
    local project_name="$2"
    local scheme_name="$3"
    local log_path="${LOGS_DIR}/ios-tests-${project_name}-$(date +%Y%m%d-%H%M%S).log"

    echo "Running iOS tests for ${project_name}..."
    if BACKEND_URL="${BACKEND_URL:-}" DISABLE_REGISTRATION="${DISABLE_REGISTRATION:-}" \
        xcodebuild -project "${project_root}/${project_name}.xcodeproj" \
        -scheme "${scheme_name}" \
        -destination "platform=iOS Simulator,name=${SIM_TARGET},OS=latest" \
        -derivedDataPath "${DERIVED_DATA_PATH}" \
        -skip-testing:"${scheme_name}UITests" \
        test >"${log_path}" 2>&1; then
        echo "iOS tests succeeded for ${project_name} (log: ${log_path})."
    else
        echo "iOS tests failed for ${project_name}. Inspect ${log_path}." >&2
        tail -n 40 "${log_path}" >&2 || true
        exit 1
    fi
}

run_android_tests() {
    if [[ ! -d "${ANDROID_APP_DIR}" ]]; then
        echo "Cannot find Android project at ${ANDROID_APP_DIR}" >&2
        exit 1
    fi
    echo "Running Android unit tests..."
    pushd "${ANDROID_APP_DIR}" >/dev/null
    BACKEND_URL="${BACKEND_URL:-}" DISABLE_REGISTRATION="${DISABLE_REGISTRATION:-}" \
        ./gradlew :app:testDebugUnitTest
    popd >/dev/null
}

if "${run_ios}"; then
    require_cmd xcodebuild
    run_ios_tests "${IOS_ROOT}/juke" "juke-iOS" "juke-iOS"
    run_ios_tests "${IOS_ROOT}/shotclock" "ShotClock" "ShotClock"
fi

if "${run_android}"; then
    require_cmd java
    run_android_tests
fi

echo "Done."
