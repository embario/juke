#!/usr/bin/env bash
# Run only against an isolated development backend and disposable test account.
# VIBE_TEST_CREDENTIALS points to private JSON {baseURL,username,password}.
set -euo pipefail
VIBE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${VIBE_TEST_CREDENTIALS:=/tmp/juke-vibe-test-credentials.json}"
export VIBE_TEST_CREDENTIALS
command -v ffmpeg >/dev/null
ffmpeg -hide_banner -loglevel error -f lavfi -i color=c=coral:s=320x240:d=1 -frames:v 1 /tmp/vibe-memory-fixture.png -y
ffmpeg -hide_banner -loglevel error -f lavfi -i color=c=indigo:s=320x240:d=1 -c:v libx264 -pix_fmt yuv420p /tmp/vibe-memory-fixture.mp4 -y
swiftc -parse-as-library \
  "$VIBE_ROOT/macos/juke/JukeMac/Models/RecognizedTrack.swift" \
  "$VIBE_ROOT/macos/juke/JukeMac/Models/MusicMemory.swift" \
  "$VIBE_ROOT/mobile/shared/JukeRadio/JukeServer.swift" \
  "$VIBE_ROOT/macos/juke/JukeMac/Services/MemoryClient.swift" \
  "$VIBE_ROOT/macos/juke/IntegrationTests/MemoryLiveCheck.swift" \
  -o /tmp/vibe-memory-live-check
/tmp/vibe-memory-live-check
