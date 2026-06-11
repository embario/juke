package transport

import (
	"context"
	"errors"

	"github.com/embario/juke/cli/internal/api"
)

// errWSNotAvailable is returned by WSTransport.Connect in Phase 1b to force
// the Manager to fall back to polling.
var errWSNotAvailable = errors.New("transport: WebSocket not available (Phase 1b stub — replaced in Phase 3)")

// WSTransport is a placeholder that always fails. When the backend WebSocket
// endpoint exists (cli-phase2) and gorilla/websocket is wired in (cli-phase3),
// this file is replaced with a real implementation.
type WSTransport struct{}

// Connect always returns errWSNotAvailable. The Manager treats this as a
// signal to activate the polling fallback.
func (w *WSTransport) Connect(_ context.Context, _ chan<- *api.PlaybackState) error {
	return errWSNotAvailable
}

// Mode returns "websocket" (the identifier, even for the stub).
func (w *WSTransport) Mode() string { return ModeWebSocket }

// Stop is a no-op for the stub.
func (w *WSTransport) Stop() {}
