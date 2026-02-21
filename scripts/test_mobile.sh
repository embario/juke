#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IOS_ROOT="${REPO_ROOT}/mobile/ios"
ANDROID_ROOT="${REPO_ROOT}/mobile/android"
source "${SCRIPT_DIR}/load_env.sh"
DERIVED_DATA_PATH="${REPO_ROOT}/.derived-data"
LOGS_DIR="${REPO_ROOT}/logs"
SIM_TARGET_DEFAULT="iPhone 17 Pro"
SIM_OS_DEFAULT="26.2"
SIM_TARGET="${SIM_TARGET:-${SIM_TARGET_DEFAULT}}"
SIM_OS="${SIM_OS:-${SIM_OS_DEFAULT}}"
PROJECT_NAME=""

usage() {
    cat <<EOF
Usage: $(basename "$0") -p <project> [-s simulator] [-o os] [--ios-only | --android-only] [--include-jukekit-tests]

Options:
  -p  Project name (required): juke, shotclock, or tunetrivia
  -s  Simulator name or UUID (default: ${SIM_TARGET_DEFAULT})
  -o  Simulator OS version (default: ${SIM_OS_DEFAULT})
  --ios-only      Run only iOS tests
  --android-only  Run only Android tests
  --include-jukekit-tests  Also run Swift package tests for mobile/ios/Packages/JukeKit
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
run_jukekit_tests=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p)
            PROJECT_NAME="$2"
            shift 2
            ;;
        -s)
            SIM_TARGET="$2"
            shift 2
            ;;
        -o)
            SIM_OS="$2"
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
        --include-jukekit-tests|--jukekit-tests)
            run_jukekit_tests=true
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

if [[ -z "${PROJECT_NAME}" ]]; then
    echo "Missing required -p <project> argument." >&2
    usage >&2
    exit 2
fi

if [[ "${PROJECT_NAME}" != "juke" && "${PROJECT_NAME}" != "shotclock" && "${PROJECT_NAME}" != "tunetrivia" ]]; then
    echo "Unsupported project '${PROJECT_NAME}'. Use 'juke', 'shotclock', or 'tunetrivia'." >&2
    exit 2
fi

ANDROID_PROJECT_NAME="${PROJECT_NAME}"
ANDROID_APP_DIR="${ANDROID_ROOT}/${ANDROID_PROJECT_NAME}"

mkdir -p "${DERIVED_DATA_PATH}" "${LOGS_DIR}"

set -x

echo "Mobile test runner"
echo "  repo: ${REPO_ROOT}"
echo "  ios: ${run_ios} (sim: ${SIM_TARGET}, os: ${SIM_OS})"
echo "  android: ${run_android} (project: ${ANDROID_PROJECT_NAME})"
echo "  juke kit tests: ${run_jukekit_tests}"
echo "  env file: ${ENV_FILE:-.env}"

run_ios_tests() {
    local project_root="$1"
    local project_name="$2"
    local scheme_name="$3"
    local log_path="${LOGS_DIR}/ios-tests-${project_name}-$(date +%Y%m%d-%H%M%S).log"
    local destination="platform=iOS Simulator,name=${SIM_TARGET}"
    local ios_backend_url="${BACKEND_URL:-http://127.0.0.1:8000}"
    local ios_disable_registration="${DISABLE_REGISTRATION:-0}"

    if command -v xcrun >/dev/null 2>&1; then
        if ! xcrun simctl list devices available | grep -F "${SIM_TARGET} (" >/dev/null 2>&1; then
            echo "Simulator '${SIM_TARGET}' is not available. Falling back to generic iOS Simulator destination."
            destination="platform=iOS Simulator"
        fi
    fi

    echo "Running iOS tests for ${project_name}..."
    echo "  destination: ${destination}"
    echo "  backend_url: ${ios_backend_url}"
    # Use destination without explicit OS version to let Xcode pick an installed runtime.
    if xcodebuild -project "${project_root}/${project_name}.xcodeproj" \
        -scheme "${scheme_name}" \
        -destination "${destination}" \
        -derivedDataPath "${DERIVED_DATA_PATH}" \
        -skip-testing:"${scheme_name}UITests" \
        BACKEND_URL="${ios_backend_url}" \
        DISABLE_REGISTRATION="${ios_disable_registration}" \
        test 2>&1 | tee "${log_path}"; then
        echo "iOS tests succeeded for ${project_name} (log: ${log_path})."
    else
        echo "iOS tests failed for ${project_name}. Inspect ${log_path}." >&2
        tail -n 40 "${log_path}" >&2 || true
        exit 1
    fi
}

run_android_tests() {
    if [[ "${ANDROID_PROJECT_NAME}" == "tunetrivia" ]]; then
        echo "Android tests are not available for tunetrivia." >&2
        exit 2
    fi
    if [[ ! -d "${ANDROID_APP_DIR}" ]]; then
        echo "Cannot find Android project at ${ANDROID_APP_DIR}" >&2
        exit 1
    fi
    echo "Running Android unit tests..."
    local log_path="${LOGS_DIR}/android-tests-${ANDROID_PROJECT_NAME}-$(date +%Y%m%d-%H%M%S).log"
    pushd "${ANDROID_APP_DIR}" >/dev/null
    BACKEND_URL="${BACKEND_URL:-}" DISABLE_REGISTRATION="${DISABLE_REGISTRATION:-}" \
        ./gradlew :app:testDebugUnitTest 2>&1 | tee "${log_path}"
    popd >/dev/null
    echo "Android tests log: ${log_path}"
}

run_jukekit_package_tests() {
    local package_root="${IOS_ROOT}/Packages/JukeKit"
    local log_path="${LOGS_DIR}/ios-tests-JukeKit-$(date +%Y%m%d-%H%M%S).log"
    local swiftpm_module_cache="${DERIVED_DATA_PATH}/swiftpm-module-cache"
    local clang_module_cache="${DERIVED_DATA_PATH}/clang-module-cache"

    if [[ ! -d "${package_root}" ]]; then
        echo "Cannot find JukeKit package at ${package_root}" >&2
        exit 1
    fi

    mkdir -p "${swiftpm_module_cache}" "${clang_module_cache}"
    echo "Running JukeKit Swift package tests..."
    pushd "${package_root}" >/dev/null
    if SWIFTPM_MODULECACHE_OVERRIDE="${swiftpm_module_cache}" \
        CLANG_MODULE_CACHE_PATH="${clang_module_cache}" \
        swift test --disable-sandbox 2>&1 | tee "${log_path}"; then
        popd >/dev/null
        echo "JukeKit tests succeeded (log: ${log_path})."
    else
        popd >/dev/null
        echo "JukeKit tests failed. Inspect ${log_path}." >&2
        tail -n 40 "${log_path}" >&2 || true
        exit 1
    fi
}

if "${run_ios}"; then
    require_cmd xcodebuild
    case "${PROJECT_NAME}" in
        juke)
            run_ios_tests "${IOS_ROOT}/juke" "juke-iOS" "juke-iOS"
            ;;
        shotclock)
            run_ios_tests "${IOS_ROOT}/shotclock" "ShotClock" "ShotClock"
            ;;
        tunetrivia)
            run_ios_tests "${IOS_ROOT}/tunetrivia" "TuneTrivia" "TuneTrivia"
            ;;
    esac
fi

if "${run_android}"; then
    require_cmd java
    run_android_tests
fi

if "${run_jukekit_tests}"; then
    require_cmd swift
    run_jukekit_package_tests
fi

echo "Done."
