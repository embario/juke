#!/usr/bin/env bash
# scripts/test_cli.sh — run all Go checks for the cli/ subproject.
# Usage: ./scripts/test_cli.sh  (from repo root or any subdirectory)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLI_DIR="$REPO_ROOT/cli"

cd "$CLI_DIR"

echo "==> go vet ./..."
go vet ./...

echo "==> go build ./cmd/..."
CGO_ENABLED=0 go build ./cmd/...

echo "==> go test -race ./..."
go test -race ./...

echo ""
echo "✓ cli checks passed"
