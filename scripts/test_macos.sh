#!/usr/bin/env bash
# Run the Juke macOS app's unit tests.
# Usage: scripts/test_macos.sh [--ui]   (--ui runs the UI automation scheme instead)
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_dir=""
for candidate in "$repo_root/macos/juke" "$repo_root/macos/jukevibe"; do
  if compgen -G "$candidate/*.xcodeproj" > /dev/null; then project_dir="$candidate"; break; fi
done
[[ -n "$project_dir" ]] || { echo "No macOS Xcode project found under macos/" >&2; exit 1; }

project="$(basename "$(compgen -G "$project_dir/*.xcodeproj" | head -1)")"
app_scheme="${project%.xcodeproj}"
scheme="$app_scheme"
[[ "${1:-}" == "--ui" ]] && scheme="${app_scheme}UIAutomation"

extra=()
if [[ -n "${CI:-}" ]]; then
  # CI runners have no signing identity; skip the tests that need a team-signed Keychain entitlement.
  extra+=(CODE_SIGNING_ALLOWED=NO "-skip-testing:${app_scheme}Tests/JukeKeychainConfigurationTests")
fi

derived="${DERIVED_DATA_PATH:-$repo_root/.build/macos-derived-data}"
cd "$project_dir"
xcodebuild -project "$project" -scheme "$scheme" -destination 'platform=macOS' \
  -derivedDataPath "$derived" ${extra[@]+"${extra[@]}"} test
