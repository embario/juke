#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IOS_ROOT="${REPO_ROOT}/mobile/ios"
IOS_PROJECT_NAME_DEFAULT="juke"
SIM_TARGET_DEFAULT="iPhone 17 Pro"
IOS_PROJECT_NAME="${IOS_PROJECT_NAME:-}"
SIM_TARGET="${SIM_TARGET:-}"
IOS_PROJECT_ROOT="${IOS_ROOT}/${IOS_PROJECT_NAME}"
DERIVED_DATA_PATH="${REPO_ROOT}/.derived-data"
LOGS_DIR="${REPO_ROOT}/logs"

usage() {
    cat <<EOF
Usage: $(basename "$0") [-p project] [-s simulator]

Options:
  -p  iOS project name under ${IOS_ROOT} (default: ${IOS_PROJECT_NAME_DEFAULT})
  -s  Simulator name or UUID (default: ${SIM_TARGET_DEFAULT})
EOF
}

list_available_projects() {
    local project
    for project in "${IOS_ROOT}"/*; do
        [[ -d "${project}" ]] || continue
        basename "${project}"
    done | sort
}

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
    IOS_PROJECT_NAME="${IOS_PROJECT_NAME_DEFAULT}"
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
    shotclock)
        XCODEPROJ_NAME="ShotClock.xcodeproj"
        SCHEME_NAME="ShotClock"
        BUNDLE_ID="embario.ShotClock"
        APP_NAME="ShotClock.app"
        ;;
    *)
        XCODEPROJ_NAME="juke-iOS.xcodeproj"
        SCHEME_NAME="juke-iOS"
        BUNDLE_ID="embario.juke-iOS"
        APP_NAME="juke-iOS.app"
        ;;
esac

PROJECT_PATH="${IOS_PROJECT_ROOT}/${XCODEPROJ_NAME}"
APP_PATH="${DERIVED_DATA_PATH}/Build/Products/Debug-iphonesimulator/${APP_NAME}"

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

mkdir -p "${DERIVED_DATA_PATH}" "${LOGS_DIR}"

echo "[1/5] Building ${PROJECT_PATH} for ${SIM_TARGET}..."
if xcodebuild -project "${PROJECT_PATH}" \
    -scheme "${SCHEME_NAME}" \
    -destination "platform=iOS Simulator,name=${SIM_TARGET},OS=latest" \
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

DEVICE_ID="$(resolve_device_id "${SIM_TARGET}")"

echo "[2/5] Booting simulator ${DEVICE_ID} (${SIM_TARGET})..."
xcrun simctl boot "${DEVICE_ID}" >/dev/null 2>&1 || true

echo "[3/5] Installing app..."
xcrun simctl install "${DEVICE_ID}" "${APP_PATH}"

echo "[4/5] Launching ${BUNDLE_ID}..."
LAUNCH_OUTPUT="$(xcrun simctl launch "${DEVICE_ID}" "${BUNDLE_ID}")"
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
