package transport

import (
	"context"
	"log"
	"sync"
	"time"

	"github.com/embario/juke/cli/internal/api"
	"github.com/embario/juke/cli/internal/ipc"
)

// Manager owns the daemon's backend connection. It tries the WebSocket
// transport first; if that fails (or is unavailable), it starts the polling
// fallback. When the active mode changes, it emits a daemon.transport.changed
// IPC broadcast so connected TUI clients can update their status indicators
// (the indicator UI lands in Phase 3 — the event is already emitted here).
type Manager struct {
	apiClient    *api.Client
	pollInterval time.Duration
	broadcast    func(ipc.Message) // IPC server Broadcast, used for transport.changed events

	mu     sync.Mutex
	mode   string
	active Transport
}

// NewManager returns a Manager that polls on the given interval. broadcast is
// called with daemon.transport.changed events; it may be nil (events are
// skipped but the manager still works).
func NewManager(client *api.Client, pollInterval time.Duration, broadcast func(ipc.Message)) *Manager {
	return &Manager{
		apiClient:    client,
		pollInterval: pollInterval,
		broadcast:    broadcast,
	}
}

// Start attempts the WebSocket transport; on failure it falls back to polling.
// It blocks until ctx is cancelled. Intended to be called in a goroutine.
// updates receives *api.PlaybackState values whenever the state changes.
func (m *Manager) Start(ctx context.Context, updates chan<- *api.PlaybackState) {
	ws := &WSTransport{}
	if err := ws.Connect(ctx, updates); err == nil {
		m.setActive(ModeWebSocket, ws)
		<-ctx.Done()
		ws.Stop()
		return
	}

	log.Printf("transport: WebSocket unavailable, switching to polling fallback")
	poll := NewPollTransport(m.apiClient, m.pollInterval)
	if err := poll.Connect(ctx, updates); err != nil {
		log.Printf("transport: failed to start polling: %v", err)
		return
	}
	m.setActive(ModePolling, poll)
	<-ctx.Done()
	poll.Stop()
}

// Mode returns the currently active transport mode string ("websocket" or
// "polling"), or "" if Start has not been called yet.
func (m *Manager) Mode() string {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.mode
}

// setActive records the new active transport and emits daemon.transport.changed.
func (m *Manager) setActive(mode string, t Transport) {
	m.mu.Lock()
	m.mode = mode
	m.active = t
	m.mu.Unlock()

	if m.broadcast != nil {
		ev, err := ipc.MsgEvent("daemon.transport.changed", map[string]string{"mode": mode})
		if err == nil {
			m.broadcast(ev)
		}
	}
}
