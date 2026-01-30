#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IOS_ROOT="${REPO_ROOT}/mobile/ios"
source "${SCRIPT_DIR}/load_env.sh"
SIM_TARGET_DEFAULT="iPhone 17 Pro"
BUILD_TIMEOUT_SECONDS="${BUILD_TIMEOUT_SECONDS:-1800}"
IOS_PROJECT_NAME="${IOS_PROJECT_NAME:-}"
SIM_TARGET="${SIM_TARGET:-}"
IOS_PROJECT_ROOT="${IOS_ROOT}/${IOS_PROJECT_NAME}"
DERIVED_DATA_PATH="${REPO_ROOT}/.derived-data"
LOGS_DIR="${REPO_ROOT}/logs"

usage() {
    cat <<EOF
Usage: $(basename "$0") -p project [-s simulator] [--boot-simulator]

Options:
  -p  iOS project name under ${IOS_ROOT} (required: juke, tunetrivia, shotclock)
  -s  Simulator name or UUID (default: ${SIM_TARGET_DEFAULT})
  --boot-simulator  Boot and target the specified simulator, even if another is booted
EOF
}

ALLOWED_PROJECTS=("juke" "tunetrivia" "shotclock")

list_available_projects() {
    local project
    for project in "${IOS_ROOT}"/*; do
        [[ -d "${project}" ]] || continue
        basename "${project}"
    done | sort
}

is_allowed_project() {
    local candidate="$1"
    local project
    for project in "${ALLOWED_PROJECTS[@]}"; do
        if [[ "${candidate}" == "${project}" ]]; then
            return 0
        fi
    done
    return 1
}

USE_BOOTED_SIM=true
FORCE_BOOT_SIM=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --boot-simulator)
            FORCE_BOOT_SIM=true
            USE_BOOTED_SIM=false
            shift
            ;;
        -p|-s|-h)
            break
            ;;
        *)
            break
            ;;
    esac
done

while getopts ":p:s:h" opt; do
    case "${opt}" in
        p)
            IOS_PROJECT_NAME="${OPTARG}"
            ;;
        s)
            SIM_TARGET="${OPTARG}"
            ;;
        h)
            usage
            exit 0
            ;;
        \?)
            echo "Unknown option: -${OPTARG}" >&2
            usage >&2
            exit 2
            ;;
        :)
            echo "Option -${OPTARG} requires an argument." >&2
            usage >&2
            exit 2
            ;;
    esac
done
shift $((OPTIND - 1))

if [[ -z "${IOS_PROJECT_NAME}" ]]; then
    echo "Missing required -p project argument." >&2
    echo "Available projects:" >&2
    list_available_projects | sed 's/^/  - /' >&2
    exit 2
fi

if ! is_allowed_project "${IOS_PROJECT_NAME}"; then
    echo "Unsupported iOS project '${IOS_PROJECT_NAME}'." >&2
    echo "Supported projects: ${ALLOWED_PROJECTS[*]}" >&2
    exit 2
fi

if [[ -z "${SIM_TARGET}" ]]; then
    SIM_TARGET="${SIM_TARGET_DEFAULT}"
fi

IOS_PROJECT_ROOT="${IOS_ROOT}/${IOS_PROJECT_NAME}"

RUN_TS="$(date +%Y%m%d-%H%M%S)"
BUILD_LOG_PATH="${LOGS_DIR}/ios-build-${IOS_PROJECT_NAME}-${RUN_TS}.log"
SIM_LOG_PATH="${LOGS_DIR}/simulator-${IOS_PROJECT_NAME}-${RUN_TS}.log"

if [[ ! -d "${IOS_PROJECT_ROOT}" ]]; then
    echo "iOS project '${IOS_PROJECT_NAME}' not found under ${IOS_ROOT}." >&2
    echo "Available projects:" >&2
    list_available_projects | sed 's/^/  - /' >&2
    exit 1
fi

# Derive project-specific values from IOS_PROJECT_NAME
case "${IOS_PROJECT_NAME}" in
    juke)
        XCODEPROJ_NAME="juke-iOS.xcodeproj"
        SCHEME_NAME="juke-iOS"
        BUNDLE_ID="embario.juke-iOS"
        APP_NAME="juke-iOS.app"
        ;;
    shotclock)
        XCODEPROJ_NAME="ShotClock.xcodeproj"
        SCHEME_NAME="ShotClock"
        BUNDLE_ID="embario.ShotClock"
        APP_NAME="ShotClock.app"
        ;;
    tunetrivia)
        XCODEPROJ_NAME="TuneTrivia.xcodeproj"
        SCHEME_NAME="TuneTrivia"
        BUNDLE_ID="embario.TuneTrivia"
        APP_NAME="TuneTrivia.app"
        ;;
    *)
        echo "Unsupported iOS project '${IOS_PROJECT_NAME}'." >&2
        exit 2
        ;;
esac

PROJECT_PATH="${IOS_PROJECT_ROOT}/${XCODEPROJ_NAME}"
APP_PATH=""

resolve_device_id() {
    local target="$1"
    if [[ "$target" =~ ^[0-9A-Fa-f-]{36}$ ]]; then
        echo "$target"
        return 0
    fi
    local line
    if ! line=$(xcrun simctl list devices available | grep -F "${target} (" | head -n 1); then
        echo "Could not find an available simulator named '${target}'." >&2
        exit 1
    fi
    echo "$line" | sed -E 's/.*\(([0-9A-Fa-f-]+)\).*/\1/'
}

resolve_booted_device() {
    local line
    if ! line=$(xcrun simctl list devices booted | grep -m 1 "Booted"); then
        return 1
    fi
    if [[ "${line}" =~ ^[[:space:]]*(.*)[[:space:]]+\(([0-9A-Fa-f-]{36})\)[[:space:]]+\(Booted\) ]]; then
        local name udid
        name="${BASH_REMATCH[1]}"
        udid="${BASH_REMATCH[2]}"
        echo "${udid}|${name}"
        return 0
    fi
    echo "Unable to parse booted simulator from: ${line}" >&2
    return 1
}

normalize_bool() {
    local value
    value="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]' | xargs)"
    case "${value}" in
        1|true|yes|on) echo "true" ;;
        *) echo "false" ;;
    esac
}

set_plist_value() {
    local plist_path="$1"
    local key="$2"
    local type="$3"
    local value="$4"
    if /usr/libexec/PlistBuddy -c "Print :${key}" "${plist_path}" >/dev/null 2>&1; then
        /usr/libexec/PlistBuddy -c "Set :${key} ${value}" "${plist_path}"
    else
        /usr/libexec/PlistBuddy -c "Add :${key} ${type} ${value}" "${plist_path}"
    fi
}

ensure_core_simulator() {
    local attempt=1
    local max_attempts=3
    local wait_seconds=2
    while [[ "${attempt}" -le "${max_attempts}" ]]; do
        echo "Checking CoreSimulator availability (attempt ${attempt}/${max_attempts})..."
        if xcrun simctl list devices available >/dev/null 2>&1; then
            return 0
        fi
        if [[ "${attempt}" -eq 1 ]]; then
            echo "CoreSimulator not responding; launching Simulator.app..."
            open -a Simulator >/dev/null 2>&1 || true
        fi
        echo "Retrying in ${wait_seconds}s..."
        sleep "${wait_seconds}"
        attempt=$((attempt + 1))
    done
    echo "CoreSimulator still unavailable after ${max_attempts} attempts." >&2
    echo "Tip: open Simulator.app once to initialize runtimes, then retry." >&2
    return 1
}

run_with_timeout() {
    local timeout_cmd=""
    if command -v gtimeout >/dev/null 2>&1; then
        timeout_cmd="gtimeout"
    elif command -v timeout >/dev/null 2>&1; then
        timeout_cmd="timeout"
    fi

    if [[ -n "${timeout_cmd}" ]]; then
        "${timeout_cmd}" "${BUILD_TIMEOUT_SECONDS}" "$@"
    else
        "$@"
    fi
}

mkdir -p "${DERIVED_DATA_PATH}" "${LOGS_DIR}"

if ! ensure_core_simulator; then
    exit 1
fi

if "${USE_BOOTED_SIM}"; then
    if BOOTED_INFO="$(resolve_booted_device)"; then
        DEVICE_ID="${BOOTED_INFO%%|*}"
        SIM_TARGET="${BOOTED_INFO##*|}"
    else
        DEVICE_ID="$(resolve_device_id "${SIM_TARGET}")"
        FORCE_BOOT_SIM=true
    fi
else
    DEVICE_ID="$(resolve_device_id "${SIM_TARGET}")"
fi
DERIVED_DATA_PATH="${DERIVED_DATA_PATH}/${IOS_PROJECT_NAME}-${DEVICE_ID}"
APP_PATH="${DERIVED_DATA_PATH}/Build/Products/Debug-iphonesimulator/${APP_NAME}"
BUILD_LOG_PATH="${LOGS_DIR}/ios-build-${IOS_PROJECT_NAME}-${DEVICE_ID}-${RUN_TS}.log"
SIM_LOG_PATH="${LOGS_DIR}/simulator-${IOS_PROJECT_NAME}-${DEVICE_ID}-${RUN_TS}.log"

echo "[1/5] Building ${PROJECT_PATH} for ${SIM_TARGET}..."
if BACKEND_URL="${BACKEND_URL:-}" DISABLE_REGISTRATION="${DISABLE_REGISTRATION:-}" \
    run_with_timeout xcodebuild -project "${PROJECT_PATH}" \
    -scheme "${SCHEME_NAME}" \
    -destination "platform=iOS Simulator,id=${DEVICE_ID}" \
    -derivedDataPath "${DERIVED_DATA_PATH}" \
    build >"${BUILD_LOG_PATH}" 2>&1; then
        echo "Build succeeded (see ${BUILD_LOG_PATH} for details)."
else
        echo "Build failed. Inspect ${BUILD_LOG_PATH} for details." >&2
        tail -n 40 "${BUILD_LOG_PATH}" >&2 || true
        exit 1
fi

if [[ ! -d "${APP_PATH}" ]]; then
    echo "App bundle not found at ${APP_PATH}" >&2
    exit 1
fi

PLIST_PATH="${APP_PATH}/Info.plist"
if [[ -f "${PLIST_PATH}" ]]; then
    echo "Injecting runtime config into Info.plist..."
    if [[ -n "${BACKEND_URL:-}" ]]; then
        set_plist_value "${PLIST_PATH}" "BACKEND_URL" "string" "${BACKEND_URL}"
    fi
    set_plist_value "${PLIST_PATH}" "DISABLE_REGISTRATION" "bool" "$(normalize_bool "${DISABLE_REGISTRATION:-}")"
fi

if "${FORCE_BOOT_SIM}"; then
    echo "[2/5] Booting simulator ${DEVICE_ID} (${SIM_TARGET})..."
    xcrun simctl boot "${DEVICE_ID}" >/dev/null 2>&1 || true
else
    echo "[2/5] Using already-booted simulator ${DEVICE_ID} (${SIM_TARGET})..."
fi

echo "[3/5] Installing app..."
xcrun simctl install "${DEVICE_ID}" "${APP_PATH}"

echo "[4/5] Launching ${BUNDLE_ID}..."
if LAUNCH_OUTPUT="$(xcrun simctl launch \
    --env DISABLE_REGISTRATION="${DISABLE_REGISTRATION:-}" \
    --env BACKEND_URL="${BACKEND_URL:-}" \
    "${DEVICE_ID}" "${BUNDLE_ID}" 2>/dev/null)"; then
    :
else
    echo "Simulator does not support --env on launch; starting without env overrides." >&2
    LAUNCH_OUTPUT="$(xcrun simctl launch "${DEVICE_ID}" "${BUNDLE_ID}")"
fi
APP_PID="$(echo "${LAUNCH_OUTPUT}" | awk '{print $NF}')"
if [[ ! "${APP_PID}" =~ ^[0-9]+$ ]]; then
    echo "Could not parse app PID from launch output: ${LAUNCH_OUTPUT}" >&2
    APP_PID=""
fi

echo "[5/5] Saving simulator logs to ${SIM_LOG_PATH}..."
if [[ -n "${APP_PID}" ]]; then
    if ! xcrun simctl spawn "${DEVICE_ID}" log show --last 2m --style compact \
        --predicate "processID == ${APP_PID}" >"${SIM_LOG_PATH}" 2>&1; then
        echo "Failed to collect simulator logs for PID ${APP_PID}." >&2
    fi
else
    if ! xcrun simctl spawn "${DEVICE_ID}" log show --last 2m --style compact >"${SIM_LOG_PATH}" 2>&1; then
        echo "Failed to collect simulator logs." >&2
    fi
fi
