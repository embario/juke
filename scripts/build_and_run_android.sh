#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ANDROID_ROOT="${REPO_ROOT}/mobile/android"
source "${SCRIPT_DIR}/load_env.sh"
ANDROID_PROJECT_NAME=""
ANDROID_APP_DIR=""
API_LEVEL="36"
SYSTEM_IMAGE="system-images;android-${API_LEVEL};google_apis;arm64-v8a"
AVD_NAME="jukeApi${API_LEVEL}"
DEVICE_PROFILE="pixel_7"
APP_ID="fm.juke.mobile"
LOG_DIR="${REPO_ROOT}/.android-emulator"

usage() {
    cat <<EOF
Usage: $(basename "$0") -p project

Options:
  -p  Android project name under ${ANDROID_ROOT} (required)
EOF
}

list_available_projects() {
    local project
    for project in "${ANDROID_ROOT}"/*; do
        [[ -d "${project}" ]] || continue
        basename "${project}"
    done | sort
}

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command '$1'. Ensure the Android SDK cmdline-tools are on your PATH." >&2
        exit 1
    fi
}

while getopts ":p:h" opt; do
    case "${opt}" in
        p)
            ANDROID_PROJECT_NAME="${OPTARG}"
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

if [[ -z "${ANDROID_PROJECT_NAME}" ]]; then
    echo "Missing required -p project argument." >&2
    echo "Available projects:" >&2
    list_available_projects | sed 's/^/  - /' >&2
    exit 2
fi

ANDROID_APP_DIR="${ANDROID_ROOT}/${ANDROID_PROJECT_NAME}"

for tool in sdkmanager avdmanager emulator adb; do
    require_cmd "$tool"
done

if [[ ! -d "${ANDROID_APP_DIR}" ]]; then
    echo "Android project '${ANDROID_PROJECT_NAME}' not found under ${ANDROID_ROOT}." >&2
    echo "Available projects:" >&2
    list_available_projects | sed 's/^/  - /' >&2
    exit 1
fi

run_with_auto_yes() {
    set +o pipefail
    yes | "$@"
    local status=$?
    set -o pipefail
    return ${status}
}

install_sdk_components() {
    echo "Ensuring Android SDK components for API ${API_LEVEL} are installed (downloads will be shown)..."
    run_with_auto_yes sdkmanager --install \
        "platform-tools" \
        "platforms;android-${API_LEVEL}" \
        "${SYSTEM_IMAGE}"
    run_with_auto_yes sdkmanager --licenses
}

ensure_avd() {
    if avdmanager list avd | grep -q "Name: ${AVD_NAME}"; then
        echo "AVD ${AVD_NAME} already exists."
        return
    fi

    echo "Creating AVD ${AVD_NAME}..."
    echo "no" | avdmanager create avd \
        -n "${AVD_NAME}" \
        -k "${SYSTEM_IMAGE}" \
        --device "${DEVICE_PROFILE}" \
        --force >/dev/null
}

emulator_running() {
    adb devices | awk 'NR>1 && $2 == "device" {print $1}' | grep -q '^emulator-'
}

start_emulator() {
    if emulator_running; then
        echo "An emulator is already running; reusing the existing instance."
        return
    fi

    mkdir -p "${LOG_DIR}"
    local log_file="${LOG_DIR}/${AVD_NAME}.log"

    echo "Starting emulator ${AVD_NAME} (logs: ${log_file})..."
    nohup emulator -avd "${AVD_NAME}" \
        -netdelay none \
        -netspeed full \
        -no-snapshot \
        -no-boot-anim \
        >"${log_file}" 2>&1 &

    echo "Waiting for the emulator to boot..."
    adb wait-for-device >/dev/null
    until adb shell getprop sys.boot_completed 2>/dev/null | grep -q "1"; do
        sleep 2
    done
    adb shell input keyevent 82 >/dev/null 2>&1 || true
    echo "Emulator is ready."
}

build_and_install() {
    pushd "${ANDROID_APP_DIR}" >/dev/null
    BACKEND_URL="${BACKEND_URL:-}" DISABLE_REGISTRATION="${DISABLE_REGISTRATION:-}" \
        ./gradlew :app:installDebug
    popd >/dev/null
}

launch_app() {
    echo "Launching ${APP_ID} on the emulator..."
    adb shell monkey -p "${APP_ID}" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
    echo "App launch command sent."
}

install_sdk_components
ensure_avd
start_emulator
build_and_install
launch_app

echo "Done."
