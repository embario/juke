// Package transport manages the daemon's connection to the Juke backend.
//
// Architecture: the Manager tries the WebSocket transport first; if that fails
// (including the Phase 1b stub which always fails) it falls back to the polling
// transport. The active transport feeds a channel of *api.PlaybackState updates;
// the daemon drains that channel and broadcasts playback.state.changed IPC events.
//
// Phase sequencing:
//   - Phase 1b: WSTransport stub + PollTransport (this package)
//   - Phase 3: WSTransport replaced with a real gorilla/websocket client
package transport

import (
	"context"

	"github.com/embario/juke/cli/internal/api"
)

// TransportMode constants identify which backend connection is active.
const (
	ModeWebSocket = "websocket"
	ModePolling   = "polling"
)

// Transport is the interface both the WebSocket client and the polling fallback
// satisfy. The daemon calls Connect once; the implementation feeds updates to
// the provided channel until the context is cancelled.
type Transport interface {
	// Connect starts the transport. It sends *api.PlaybackState values to
	// updates whenever the playback state changes. Returns an error immediately
	// if the transport cannot be started (e.g. WS handshake failure); returns
	// nil if the transport started successfully, even if it later encounters
	// transient errors (those are logged and retried internally).
	Connect(ctx context.Context, updates chan<- *api.PlaybackState) error

	// Mode returns the transport identifier ("websocket" or "polling").
	Mode() string

	// Stop signals the transport to cease sending updates. The context passed
	// to Connect is the primary cancellation signal; Stop is a supplementary
	// mechanism for early teardown without cancelling the parent context.
	Stop()
}
