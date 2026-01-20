#!/usr/bin/env bash
set -euo pipefail

SIM_TARGET="${1:-iPhone 17 Pro}"
BUNDLE_ID="embario.juke-iOS"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_PATH="${REPO_ROOT}/mobile/ios/juke-iOS.xcodeproj"
DERIVED_DATA_PATH="${REPO_ROOT}/.derived-data"
APP_PATH="${DERIVED_DATA_PATH}/Build/Products/Debug-iphonesimulator/juke-iOS.app"

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

mkdir -p "${DERIVED_DATA_PATH}"

echo "[1/4] Building ${PROJECT_PATH} for ${SIM_TARGET}..."
if xcodebuild -project "${PROJECT_PATH}" \
    -scheme juke-iOS \
    -destination "platform=iOS Simulator,name=${SIM_TARGET},OS=latest" \
    -derivedDataPath "${DERIVED_DATA_PATH}" \
    build >/tmp/juke-ios-build.log 2>&1; then
        echo "Build succeeded (see /tmp/juke-ios-build.log for details)."
else
        echo "Build failed. Inspect /tmp/juke-ios-build.log for details." >&2
        tail -n 40 /tmp/juke-ios-build.log >&2 || true
        exit 1
fi

if [[ ! -d "${APP_PATH}" ]]; then
    echo "App bundle not found at ${APP_PATH}" >&2
    exit 1
fi

DEVICE_ID="$(resolve_device_id "${SIM_TARGET}")"

echo "[2/4] Booting simulator ${DEVICE_ID} (${SIM_TARGET})..."
xcrun simctl boot "${DEVICE_ID}" >/dev/null 2>&1 || true

echo "[3/4] Installing app..."
xcrun simctl install "${DEVICE_ID}" "${APP_PATH}"

echo "[4/4] Launching ${BUNDLE_ID}..."
xcrun simctl launch "${DEVICE_ID}" "${BUNDLE_ID}"
