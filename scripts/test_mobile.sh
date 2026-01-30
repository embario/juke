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
Usage: $(basename "$0") -p <project> [-s simulator] [-o os] [--ios-only | --android-only]

Options:
  -p  Project name (required): juke, shotclock, or tunetrivia
  -s  Simulator name or UUID (default: ${SIM_TARGET_DEFAULT})
  -o  Simulator OS version (default: ${SIM_OS_DEFAULT})
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
        -destination "platform=iOS Simulator,name=${SIM_TARGET},OS=${SIM_OS}" \
        -derivedDataPath "${DERIVED_DATA_PATH}" \
        -skip-testing:"${scheme_name}UITests" \
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

echo "Done."
