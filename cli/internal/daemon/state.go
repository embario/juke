// Package daemon wires the daemon's subsystems together and owns all in-memory
// state shared between IPC handlers.
package daemon

import (
	"sync"

	"github.com/embario/juke/cli/internal/api"
)

// SessionSnapshot is the read-only view of session state sent to IPC clients.
type SessionSnapshot struct {
	Authenticated bool   `json:"authenticated"`
	Username      string `json:"username,omitempty"`
}

// State holds the daemon's in-memory session state. All methods are
// goroutine-safe; handlers and the transport layer share this struct.
type State struct {
	mu            sync.RWMutex
	authenticated bool
	username      string
	token         string
	playback      *api.PlaybackState // nil when nothing is playing or Spotify is disconnected
}

// SetSession marks the user as authenticated and stores credentials.
func (s *State) SetSession(username, token string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.authenticated = true
	s.username = username
	s.token = token
}

// ClearSession marks the user as logged out and zeroes credentials.
func (s *State) ClearSession() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.authenticated = false
	s.username = ""
	s.token = ""
}

// Session returns a read-only snapshot of the current session state.
func (s *State) Session() SessionSnapshot {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return SessionSnapshot{
		Authenticated: s.authenticated,
		Username:      s.username,
	}
}

// Token returns the current auth token (empty if not authenticated).
func (s *State) Token() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.token
}

// SetPlaybackState stores the most-recent playback state from the transport
// layer. Passing nil is valid and means "not playing / Spotify disconnected".
func (s *State) SetPlaybackState(state *api.PlaybackState) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.playback = state
}

// PlaybackState returns the cached playback state. Returns nil when no state
// has been received yet, or when the last known state was "not playing".
func (s *State) PlaybackState() *api.PlaybackState {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.playback
}
