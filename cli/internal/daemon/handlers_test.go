package daemon_test

import (
	"encoding/json"
	"path/filepath"
	"testing"

	"github.com/embario/juke/cli/internal/daemon"
	"github.com/embario/juke/cli/internal/ipc"
)

func makeReq(id int, typ string, data any) ipc.Message {
	raw, _ := json.Marshal(data)
	i := id
	return ipc.Message{ID: &i, Type: typ, Data: raw}
}

// TestHandleSessionStateUnauthenticated verifies the handler returns
// authenticated=false for a fresh (empty) state.
func TestHandleSessionStateUnauthenticated(t *testing.T) {
	t.Parallel()
	state := &daemon.State{}
	req := makeReq(1, "session.state", map[string]any{})
	resp := daemon.HandleSessionState(req, state)
	if resp == nil {
		t.Fatal("nil response")
	}
	if resp.Type != "ok" {
		t.Errorf("type: got %q, want ok", resp.Type)
	}
	var snap daemon.SessionSnapshot
	if err := json.Unmarshal(resp.Data, &snap); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if snap.Authenticated {
		t.Error("authenticated should be false for empty state")
	}
}

// TestHandleSessionStateAuthenticated verifies the handler returns
// authenticated=true and the username after SetSession.
func TestHandleSessionStateAuthenticated(t *testing.T) {
	t.Parallel()
	state := &daemon.State{}
	state.SetSession("melodyqueen", "tok123")

	req := makeReq(2, "session.state", map[string]any{})
	resp := daemon.HandleSessionState(req, state)
	if resp == nil {
		t.Fatal("nil response")
	}
	var snap daemon.SessionSnapshot
	if err := json.Unmarshal(resp.Data, &snap); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if !snap.Authenticated {
		t.Error("authenticated should be true after SetSession")
	}
	if snap.Username != "melodyqueen" {
		t.Errorf("username: got %q, want melodyqueen", snap.Username)
	}
}

// TestHandleSessionLoginSuccess verifies that a successful login updates state,
// writes the session file, and broadcasts session.changed.
func TestHandleSessionLoginSuccess(t *testing.T) {
	t.Parallel()
	state := &daemon.State{}
	sessPath := filepath.Join(t.TempDir(), "session.json")

	var broadcasts []ipc.Message
	broadcast := func(m ipc.Message) { broadcasts = append(broadcasts, m) }

	mockLogin := func(u, p string) (string, error) {
		if u == "melodyqueen" && p == "hunter2" {
			return "realtoken", nil
		}
		return "", nil
	}

	req := makeReq(3, "session.login", map[string]string{
		"username": "melodyqueen",
		"password": "hunter2",
	})
	resp := daemon.HandleSessionLogin(req, state, sessPath, mockLogin, broadcast)

	if resp == nil {
		t.Fatal("nil response")
	}
	if resp.Type != "ok" {
		t.Errorf("type: got %q, want ok", resp.Type)
	}
	if !state.Session().Authenticated {
		t.Error("state should be authenticated after login")
	}
	if state.Token() != "realtoken" {
		t.Errorf("token: got %q, want realtoken", state.Token())
	}
	if len(broadcasts) != 1 {
		t.Errorf("broadcasts: got %d, want 1", len(broadcasts))
	}
	if len(broadcasts) > 0 && broadcasts[0].Type != "session.changed" {
		t.Errorf("broadcast type: got %q, want session.changed", broadcasts[0].Type)
	}
}

// TestHandleSessionLoginFailure verifies that a failed login leaves state
// unchanged and does not broadcast.
func TestHandleSessionLoginFailure(t *testing.T) {
	t.Parallel()
	state := &daemon.State{}
	sessPath := filepath.Join(t.TempDir(), "session.json")

	var broadcasts []ipc.Message
	broadcast := func(m ipc.Message) { broadcasts = append(broadcasts, m) }

	mockLogin := func(u, p string) (string, error) {
		return "", &apiError{400, "invalid credentials"}
	}

	req := makeReq(4, "session.login", map[string]string{
		"username": "bad",
		"password": "wrong",
	})
	resp := daemon.HandleSessionLogin(req, state, sessPath, mockLogin, broadcast)

	if resp == nil {
		t.Fatal("nil response")
	}
	if resp.Type != "error" {
		t.Errorf("type: got %q, want error", resp.Type)
	}
	if state.Session().Authenticated {
		t.Error("state should remain unauthenticated after failed login")
	}
	if len(broadcasts) != 0 {
		t.Errorf("no broadcasts expected on failure, got %d", len(broadcasts))
	}
}

// TestHandleSessionLogout verifies that logout clears state and broadcasts.
func TestHandleSessionLogout(t *testing.T) {
	t.Parallel()
	state := &daemon.State{}
	state.SetSession("melodyqueen", "tok123")
	sessPath := filepath.Join(t.TempDir(), "session.json")

	var broadcasts []ipc.Message
	broadcast := func(m ipc.Message) { broadcasts = append(broadcasts, m) }

	req := makeReq(5, "session.logout", map[string]any{})
	resp := daemon.HandleSessionLogout(req, state, sessPath, func() error { return nil }, broadcast)

	if resp == nil {
		t.Fatal("nil response")
	}
	if resp.Type != "ok" {
		t.Errorf("type: got %q, want ok", resp.Type)
	}
	if state.Session().Authenticated {
		t.Error("state should be unauthenticated after logout")
	}
	if state.Token() != "" {
		t.Errorf("token should be empty after logout, got %q", state.Token())
	}
	if len(broadcasts) != 1 || broadcasts[0].Type != "session.changed" {
		t.Errorf("expected one session.changed broadcast, got %v", broadcasts)
	}
}

// apiError is a minimal error type for tests.
type apiError struct {
	Code    int
	Message string
}

func (e *apiError) Error() string { return e.Message }
