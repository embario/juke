// Package daemon wires the daemon's subsystems together and owns all in-memory
// state shared between IPC handlers.
package daemon

import "sync"

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
