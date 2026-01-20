#!/usr/bin/env bash
set -euo pipefail

xcrun simctl spawn booted log stream --level debug --predicate 'subsystem == "com.embario.juke" AND category == "APIClient"'
