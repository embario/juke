#!/usr/bin/env bash
set -euo pipefail

# Root directory to scan (default: current directory)
ROOT_DIR="${1:-.}"

# Directories to exclude from search
EXCLUDE_DIRS=(
  node_modules
  bin
  lib
  dist
  build
  .git
  .venv
  venv
  __pycache__
  .mypy_cache
  .pytest_cache
)

# Build the prune expression for excluded directories
PRUNE_EXPR=()
for dir in "${EXCLUDE_DIRS[@]}"; do
  PRUNE_EXPR+=( -path "*/$dir" -o -path "*/$dir/*" )
done

# Helper to count files matching a find -name pattern
count_pattern() {
  local pattern="$1"
  find "$ROOT_DIR" \
    \( "${PRUNE_EXPR[@]}" \) -prune -o \
    -type f -name "$pattern" -print \
  | wc -l | tr -d ' '
}

# Language breakdown (adjust as needed)
PY_COUNT="$(count_pattern "*.py")"
TS_COUNT="$(find "$ROOT_DIR" \( "${PRUNE_EXPR[@]}" \) -prune -o -type f \( -name "*.ts" -o -name "*.tsx" \) -print | wc -l | tr -d ' ')"
JS_COUNT="$(find "$ROOT_DIR" \( "${PRUNE_EXPR[@]}" \) -prune -o -type f \( -name "*.js" -o -name "*.jsx" \) -print | wc -l | tr -d ' ')"
HTML_COUNT="$(count_pattern "*.html")"
CSS_COUNT="$(count_pattern "*.css")"
SWIFT_COUNT="$(count_pattern "*.swift")"
KOTLIN_COUNT="$(find "$ROOT_DIR" \( "${PRUNE_EXPR[@]}" \) -prune -o -type f \( -name "*.kt" -o -name "*.kts" \) -print | wc -l | tr -d ' ')"
JAVA_COUNT="$(count_pattern "*.java")"
OBJC_COUNT="$(find "$ROOT_DIR" \( "${PRUNE_EXPR[@]}" \) -prune -o -type f \( -name "*.m" -o -name "*.mm" \) -print | wc -l | tr -d ' ')"

TOTAL=$(( PY_COUNT + TS_COUNT + JS_COUNT + HTML_COUNT + CSS_COUNT + SWIFT_COUNT + KOTLIN_COUNT + JAVA_COUNT + OBJC_COUNT ))

printf "Root: %s\n" "$ROOT_DIR"
printf "Excluded dirs: %s\n\n" "$(IFS=', '; echo "${EXCLUDE_DIRS[*]}")"

printf "Breakdown:\n"
printf "  Python       : %d\n" "$PY_COUNT"
printf "  TypeScript   : %d\n" "$TS_COUNT"
printf "  JavaScript   : %d\n" "$JS_COUNT"
printf "  HTML         : %d\n" "$HTML_COUNT"
printf "  CSS          : %d\n" "$CSS_COUNT"
printf "  Swift        : %d\n" "$SWIFT_COUNT"
printf "  Kotlin       : %d\n" "$KOTLIN_COUNT"
printf "  Java         : %d\n" "$JAVA_COUNT"
printf "  Objective-C  : %d\n" "$OBJC_COUNT"
printf "\nTotal source files: %d\n" "$TOTAL"
