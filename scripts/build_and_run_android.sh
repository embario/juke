#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ANDROID_ROOT="${REPO_ROOT}/mobile/android"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
source "${SCRIPT_DIR}/load_env.sh"
ANDROID_PROJECT_NAME=""
ANDROID_APP_DIR=""
API_LEVEL="36"
SYSTEM_IMAGE="system-images;android-${API_LEVEL};google_apis;arm64-v8a"
AVD_NAME="jukeApi${API_LEVEL}"
DEVICE_PROFILE="pixel_7"
APP_ID=""
LOG_DIR="${REPO_ROOT}/.android-emulator"
LOGS_DIR="${REPO_ROOT}/logs"
BUILD_TIMEOUT_SECONDS="${BUILD_TIMEOUT_SECONDS:-1800}"
EMULATOR_SERIAL=""
EMULATOR_PID=""
RUN_TS=""
BUILD_LOG_PATH=""
EMULATOR_LOG_PATH=""
LOGCAT_PATH=""
USE_RUNNING_EMULATOR=true
FORCE_BOOT_EMULATOR=false
ANDROID_SDK_ROOT=""
SDKMANAGER=""
AVDMANAGER=""
EMULATOR=""
ADB=""
EMULATOR_GPU_MODE="${EMULATOR_GPU_MODE:-host}"
TRANSLATE_ANDROID_HOSTS="${TRANSLATE_ANDROID_HOSTS:-true}"

translate_android_host() {
    local url="$1"
    if [[ -z "${url}" ]]; then
        echo "${url}"
        return 0
    fi
    echo "${url}" | sed -E 's#(https?://)(localhost|127\\.0\\.0\\.1)#\\110.0.2.2#g'
}

apply_android_env_overrides() {
    if [[ "${TRANSLATE_ANDROID_HOSTS}" != "true" ]]; then
        return 0
    fi
    if [[ -n "${BACKEND_URL:-}" ]]; then
        BACKEND_URL="$(translate_android_host "${BACKEND_URL}")"
        export BACKEND_URL
    fi
    if [[ -n "${FRONTEND_URL:-}" ]]; then
        FRONTEND_URL="$(translate_android_host "${FRONTEND_URL}")"
        export FRONTEND_URL
    fi
}

apply_android_env_overrides

usage() {
    cat <<EOF
Usage: $(basename "$0") -p project [--boot-emulator]

Options:
  -p  Android project name under ${ANDROID_ROOT} (required: juke, tunetrivia, shotclock)
  --boot-emulator  Hard-stop any running emulators, then boot and target the configured AVD (applies DNS flags)
EOF
    echo
    echo "Available projects:"
    list_available_projects | sed 's/^/  - /'
}

ALLOWED_PROJECTS=("juke" "tunetrivia" "shotclock")

list_available_projects() {
    local project
    for project in "${ANDROID_ROOT}"/*; do
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

require_cmd() {
    local name="$1"
    local path="${2:-}"
    if [[ -n "${path}" && -x "${path}" ]]; then
        return 0
    fi
    if ! command -v "${name}" >/dev/null 2>&1; then
        echo "Missing required command '${name}'. Ensure the Android SDK cmdline-tools are on your PATH." >&2
        exit 1
    fi
}

resolve_android_sdk_root() {
    if [[ -n "${ANDROID_SDK_ROOT:-}" && -d "${ANDROID_SDK_ROOT}" ]]; then
        echo "${ANDROID_SDK_ROOT}"
        return 0
    fi
    if [[ -n "${ANDROID_HOME:-}" && -d "${ANDROID_HOME}" ]]; then
        echo "${ANDROID_HOME}"
        return 0
    fi
    if [[ -d "${HOME}/Library/Android/sdk" ]]; then
        echo "${HOME}/Library/Android/sdk"
        return 0
    fi
    if [[ -d "${HOME}/Android/Sdk" ]]; then
        echo "${HOME}/Android/Sdk"
        return 0
    fi
    return 1
}

find_cmdline_tools_bin() {
    local sdk_root="$1"
    local latest="${sdk_root}/cmdline-tools/latest/bin"
    if [[ -d "${latest}" ]]; then
        echo "${latest}"
        return 0
    fi
    local best
    best="$(ls -1d "${sdk_root}/cmdline-tools/"*/bin 2>/dev/null | sort -V | tail -n 1)"
    if [[ -n "${best}" && -d "${best}" ]]; then
        echo "${best}"
        return 0
    fi
    return 1
}

refresh_android_tools() {
    local cmdline_bin=""
    if [[ -n "${ANDROID_SDK_ROOT}" ]]; then
        cmdline_bin="$(find_cmdline_tools_bin "${ANDROID_SDK_ROOT}" || true)"
    fi
    if [[ -n "${cmdline_bin}" ]]; then
        SDKMANAGER="${cmdline_bin}/sdkmanager"
        AVDMANAGER="${cmdline_bin}/avdmanager"
    else
        SDKMANAGER="$(command -v sdkmanager || true)"
        AVDMANAGER="$(command -v avdmanager || true)"
    fi
    if [[ -n "${ANDROID_SDK_ROOT}" && -x "${ANDROID_SDK_ROOT}/emulator/emulator" ]]; then
        EMULATOR="${ANDROID_SDK_ROOT}/emulator/emulator"
    else
        EMULATOR="$(command -v emulator || true)"
    fi
    if [[ -n "${ANDROID_SDK_ROOT}" && -x "${ANDROID_SDK_ROOT}/platform-tools/adb" ]]; then
        ADB="${ANDROID_SDK_ROOT}/platform-tools/adb"
    else
        ADB="$(command -v adb || true)"
    fi
}

export_android_env() {
    if [[ -z "${ANDROID_SDK_ROOT}" ]]; then
        return 0
    fi
    export ANDROID_SDK_ROOT
    export ANDROID_HOME="${ANDROID_SDK_ROOT}"
    local cmdline_bin
    cmdline_bin="$(find_cmdline_tools_bin "${ANDROID_SDK_ROOT}" || true)"
    if [[ -n "${cmdline_bin}" ]]; then
        export PATH="${cmdline_bin}:${PATH}"
    fi
}

bootstrap_cmdline_tools() {
    if [[ -z "${ANDROID_SDK_ROOT}" ]]; then
        return 0
    fi
    local latest_bin="${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin"
    if [[ -d "${latest_bin}" ]]; then
        return 0
    fi
    local bootstrap_sdkmanager
    bootstrap_sdkmanager="$(command -v sdkmanager || true)"
    if [[ -z "${bootstrap_sdkmanager}" ]]; then
        echo "Android SDK cmdline-tools not found; cannot install cmdline-tools;latest." >&2
        return 1
    fi
    echo "Installing Android cmdline-tools;latest to align SDK XML versions..."
    yes | "${bootstrap_sdkmanager}" --install "cmdline-tools;latest"
    return 0
}

ensure_cmdline_tools_latest() {
    if [[ -z "${ANDROID_SDK_ROOT}" ]]; then
        return 0
    fi
    local latest_bin="${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin"
    if [[ -d "${latest_bin}" ]]; then
        if [[ "${SDKMANAGER}" != "${latest_bin}/sdkmanager" ]]; then
            SDKMANAGER="${latest_bin}/sdkmanager"
            AVDMANAGER="${latest_bin}/avdmanager"
        fi
        return 0
    fi
    bootstrap_cmdline_tools || return 1
    refresh_android_tools
    if [[ -d "${latest_bin}" ]]; then
        SDKMANAGER="${latest_bin}/sdkmanager"
        AVDMANAGER="${latest_bin}/avdmanager"
    fi
}

print_toolchain_info() {
    echo "Android SDK root: ${ANDROID_SDK_ROOT:-<not set>}"
    if [[ -n "${ANDROID_SDK_ROOT}" ]]; then
        local props="${ANDROID_SDK_ROOT}/cmdline-tools/latest/source.properties"
        if [[ -f "${props}" ]]; then
            local rev
            rev="$(grep -m1 '^Pkg.Revision=' "${props}" | cut -d= -f2)"
            if [[ -n "${rev}" ]]; then
                echo "cmdline-tools latest revision: ${rev}"
            fi
        fi
    fi
    if [[ -n "${SDKMANAGER}" ]]; then
        local ver
        ver="$("${SDKMANAGER}" --version 2>/dev/null | head -n 1)"
        if [[ -n "${ver}" ]]; then
            echo "sdkmanager version: ${ver}"
        fi
    fi
    echo "sdkmanager: ${SDKMANAGER}"
    echo "avdmanager: ${AVDMANAGER}"
    echo "emulator: ${EMULATOR}"
    echo "adb: ${ADB}"
}
while [[ $# -gt 0 ]]; do
    case "$1" in
        --boot-emulator)
            FORCE_BOOT_EMULATOR=true
            USE_RUNNING_EMULATOR=false
            shift
            ;;
        -p)
            if [[ -z "${2:-}" ]]; then
                echo "Option -p requires an argument." >&2
                usage >&2
                exit 2
            fi
            ANDROID_PROJECT_NAME="${2}"
            shift 2
            ;;
        -h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: ${1}" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "${ANDROID_PROJECT_NAME}" ]]; then
    echo "Missing required -p project argument." >&2
    echo "Available projects:" >&2
    list_available_projects | sed 's/^/  - /' >&2
    exit 2
fi

if ! is_allowed_project "${ANDROID_PROJECT_NAME}"; then
    echo "Unsupported Android project '${ANDROID_PROJECT_NAME}'." >&2
    echo "Supported projects: ${ALLOWED_PROJECTS[*]}" >&2
    exit 2
fi

ANDROID_APP_DIR="${ANDROID_ROOT}/${ANDROID_PROJECT_NAME}"

ANDROID_SDK_ROOT="$(resolve_android_sdk_root || true)"
refresh_android_tools
ensure_cmdline_tools_latest || true
export_android_env

require_cmd "sdkmanager" "${SDKMANAGER}"
require_cmd "avdmanager" "${AVDMANAGER}"
require_cmd "emulator" "${EMULATOR}"
require_cmd "adb" "${ADB}"

print_toolchain_info

if [[ ! -d "${ANDROID_APP_DIR}" ]]; then
    echo "Android project '${ANDROID_PROJECT_NAME}' not found under ${ANDROID_ROOT}." >&2
    echo "Available projects:" >&2
    list_available_projects | sed 's/^/  - /' >&2
    exit 1
fi

RUN_TS="$(date +%Y%m%d-%H%M%S)"
BUILD_LOG_PATH="${LOGS_DIR}/android-build-${ANDROID_PROJECT_NAME}-${RUN_TS}.log"
EMULATOR_LOG_PATH="${LOGS_DIR}/emulator-${AVD_NAME}-${RUN_TS}.log"
LOGCAT_PATH="${LOGS_DIR}/logcat-${ANDROID_PROJECT_NAME}-${RUN_TS}.log"
mkdir -p "${LOG_DIR}" "${LOGS_DIR}"

resolve_app_id() {
    local gradle_file="${ANDROID_APP_DIR}/app/build.gradle.kts"
    if [[ ! -f "${gradle_file}" ]]; then
        echo "Cannot find ${gradle_file} to resolve applicationId." >&2
        exit 1
    fi
    APP_ID=$(grep -m1 'applicationId' "${gradle_file}" | sed 's/.*"\(.*\)".*/\1/')
    if [[ -z "${APP_ID}" ]]; then
        echo "Could not parse applicationId from ${gradle_file}." >&2
        exit 1
    fi
    echo "Resolved applicationId: ${APP_ID}"
}

resolve_app_id

run_with_auto_yes() {
    set +o pipefail
    yes | "$@"
    local status=$?
    set -o pipefail
    return ${status}
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

install_sdk_components() {
    echo "Ensuring Android SDK components for API ${API_LEVEL} are installed (downloads will be shown)..."
    run_with_auto_yes "${SDKMANAGER}" --install \
        "platform-tools" \
        "platforms;android-${API_LEVEL}" \
        "${SYSTEM_IMAGE}"
    run_with_auto_yes "${SDKMANAGER}" --licenses
}

ensure_avd() {
    if "${AVDMANAGER}" list avd | grep -q "Name: ${AVD_NAME}"; then
        echo "AVD ${AVD_NAME} already exists."
        return
    fi

    echo "Creating AVD ${AVD_NAME}..."
    echo "no" | "${AVDMANAGER}" create avd \
        -n "${AVD_NAME}" \
        -k "${SYSTEM_IMAGE}" \
        --device "${DEVICE_PROFILE}" \
        --force >/dev/null
}

emulator_running() {
    "${ADB}" devices | awk 'NR>1 && $2 == "device" {print $1}' | grep -q '^emulator-'
}

stop_running_emulators() {
    local serials=()
    while IFS= read -r line; do
        [[ -n "${line}" ]] || continue
        serials+=("${line}")
    done < <("${ADB}" devices | awk 'NR>1 && $2 == "device" && $1 ~ /^emulator-/ {print $1}')

    if [[ "${#serials[@]}" -eq 0 ]]; then
        return 0
    fi

    echo "Stopping running emulators..."
    for serial in "${serials[@]}"; do
        "${ADB}" -s "${serial}" emu kill >/dev/null 2>&1 || true
    done

    local attempt=0
    while emulator_running && [[ ${attempt} -lt 15 ]]; do
        sleep 1
        attempt=$((attempt + 1))
    done
}

resolve_emulator_serial_for_avd() {
    "${ADB}" devices -l | awk -v avd="${AVD_NAME}" '$2 == "device" && $0 ~ ("avd:" avd) {print $1; exit}'
}

resolve_running_emulator() {
    local serial
    serial="$(resolve_emulator_serial_for_avd)"
    if [[ -n "${serial}" ]]; then
        echo "${serial}"
        return 0
    fi
    "${ADB}" devices | awk 'NR>1 && $2 == "device" {print $1; exit}'
}

adb_cmd() {
    if [[ -n "${EMULATOR_SERIAL}" ]]; then
        "${ADB}" -s "${EMULATOR_SERIAL}" "$@"
    else
        "${ADB}" "$@"
    fi
}

start_emulator() {
    if "${FORCE_BOOT_EMULATOR}"; then
        echo "Booting with --boot-emulator: any running emulators will be terminated."
        stop_running_emulators
    fi

    if "${USE_RUNNING_EMULATOR}" && emulator_running; then
        EMULATOR_SERIAL="$(resolve_running_emulator)"
        echo "An emulator is already running; reusing ${EMULATOR_SERIAL:-the existing instance}."
        echo "Note: emulator startup flags (including DNS) are not applied when reusing a running instance."
        echo "Reusing running emulator; no emulator stdout captured." >"${EMULATOR_LOG_PATH}"
        return
    fi

    echo "Starting emulator ${AVD_NAME} (logs: ${EMULATOR_LOG_PATH})..."
    nohup "${EMULATOR}" -avd "${AVD_NAME}" \
        -netdelay none \
        -netspeed full \
        -no-snapshot \
        -no-boot-anim \
        -gpu "${EMULATOR_GPU_MODE}" \
        -dns-server 8.8.8.8,1.1.1.1 \
        >"${EMULATOR_LOG_PATH}" 2>&1 &
    EMULATOR_PID=$!
    echo "Emulator PID: ${EMULATOR_PID}"

    echo "Waiting for the emulator to boot..."
    "${ADB}" wait-for-device >/dev/null
    until "${ADB}" shell getprop sys.boot_completed 2>/dev/null | grep -q "1"; do
        sleep 2
    done
    EMULATOR_SERIAL="$(resolve_emulator_serial_for_avd)"
    adb_cmd shell input keyevent 82 >/dev/null 2>&1 || true
    echo "Emulator is ready."
}

build_and_install() {
    # The Android emulator's loopback (127.0.0.1) is isolated from the host.
    # Rewrite to 10.0.2.2 so the app can reach the host backend.
    local emu_backend_url="${BACKEND_URL:-}"
    emu_backend_url="${emu_backend_url//127.0.0.1/10.0.2.2}"
    emu_backend_url="${emu_backend_url//localhost/10.0.2.2}"
    local emu_frontend_url="${FRONTEND_URL:-${emu_backend_url}}"
    emu_frontend_url="${emu_frontend_url//127.0.0.1/10.0.2.2}"
    emu_frontend_url="${emu_frontend_url//localhost/10.0.2.2}"

    pushd "${ANDROID_APP_DIR}" >/dev/null
    echo "Building and installing (logs: ${BUILD_LOG_PATH})..."
    if [[ -n "${APP_ID}" ]]; then
        adb_cmd shell am force-stop "${APP_ID}" >/dev/null 2>&1 || true
    fi
    if ANDROID_SERIAL="${EMULATOR_SERIAL:-}" BACKEND_URL="${emu_backend_url}" FRONTEND_URL="${emu_frontend_url}" DISABLE_REGISTRATION="${DISABLE_REGISTRATION:-}" \
        run_with_timeout ./gradlew :app:installDebug >"${BUILD_LOG_PATH}" 2>&1; then
        echo "Build/install succeeded."
    else
        echo "Build/install failed. Inspect ${BUILD_LOG_PATH} for details." >&2
        tail -n 40 "${BUILD_LOG_PATH}" >&2 || true
        exit 1
    fi
    popd >/dev/null
}

launch_app() {
    echo "Launching ${APP_ID} on the emulator..."
    adb_cmd shell monkey -p "${APP_ID}" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true

    local attempt=0
    while [[ ${attempt} -lt 6 ]]; do
        APP_PID="$(adb_cmd shell pidof -s "${APP_ID}" 2>/dev/null | tr -d '\r' || true)"
        if [[ -n "${APP_PID}" ]]; then
            echo "App PID: ${APP_PID}"
            echo "App launch command sent."
            return 0
        fi
        if [[ ${attempt} -eq 1 ]]; then
            adb_cmd shell am start -n "${APP_ID}/.MainActivity" >/dev/null 2>&1 || true
        fi
        sleep 1
        attempt=$((attempt + 1))
    done

    echo "App PID not found; launch may have failed." >&2
    return 1
}

collect_logcat() {
    echo "Saving logcat to ${LOGCAT_PATH}..."
    if [[ -n "${APP_PID:-}" ]]; then
        if ! adb_cmd logcat -d --pid "${APP_PID}" -v time >"${LOGCAT_PATH}" 2>&1; then
            adb_cmd logcat -d -v time >"${LOGCAT_PATH}" 2>&1 || true
        fi
    else
        adb_cmd logcat -d -v time >"${LOGCAT_PATH}" 2>&1 || true
    fi
}

install_sdk_components
ensure_avd
start_emulator
build_and_install
launch_app || true
collect_logcat

echo "Done."
