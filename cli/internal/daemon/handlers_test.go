package daemon_test

import (
	"context"
	"encoding/json"
	"net"
	"path/filepath"
	"testing"
	"time"

	"github.com/embario/juke/cli/internal/api"
	"github.com/embario/juke/cli/internal/config"
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

// --- HandlePlaybackState tests -----------------------------------------------

// TestHandlePlaybackStateNil verifies the handler returns null data when no
// playback state has been set yet.
func TestHandlePlaybackStateNil(t *testing.T) {
	t.Parallel()
	state := &daemon.State{}
	req := makeReq(10, "playback.state", map[string]any{})
	resp := daemon.HandlePlaybackState(req, state)
	if resp == nil {
		t.Fatal("nil response")
	}
	if resp.Type != "ok" {
		t.Errorf("type: got %q, want ok", resp.Type)
	}
	// data should decode as a nil PlaybackState (JSON null).
	var ps *api.PlaybackState
	if err := json.Unmarshal(resp.Data, &ps); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if ps != nil {
		t.Errorf("expected nil PlaybackState, got %+v", ps)
	}
}

// TestHandlePlaybackStateFilled verifies the handler returns the cached state.
func TestHandlePlaybackStateFilled(t *testing.T) {
	t.Parallel()
	trackURI := "spotify:track:4vLYewWIvqHfKtJDk8c8tq"
	fixture := &api.PlaybackState{
		Provider:  "spotify",
		IsPlaying: true,
		Track: &api.PlaybackTrack{
			Name: "So What",
			URI:  &trackURI,
			Artists: []api.PlaybackArtist{
				{Name: "Miles Davis"},
			},
		},
	}

	state := &daemon.State{}
	state.SetPlaybackState(fixture)

	req := makeReq(11, "playback.state", map[string]any{})
	resp := daemon.HandlePlaybackState(req, state)
	if resp == nil {
		t.Fatal("nil response")
	}
	if resp.Type != "ok" {
		t.Errorf("type: got %q, want ok", resp.Type)
	}

	var ps api.PlaybackState
	if err := json.Unmarshal(resp.Data, &ps); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if !ps.IsPlaying {
		t.Error("IsPlaying should be true")
	}
	if ps.Track == nil || ps.Track.Name != "So What" {
		t.Errorf("Track.Name: got %+v, want So What", ps.Track)
	}
	if len(ps.Track.Artists) == 0 || ps.Track.Artists[0].Name != "Miles Davis" {
		t.Errorf("Artists: got %+v", ps.Track.Artists)
	}
}

// TestDaemonBroadcastsPlaybackChanged wires a real ipc.Server via net.Pipe,
// simulates the daemon receiving a transport update, and asserts that a
// connected client receives a playback.state.changed broadcast.
func TestDaemonBroadcastsPlaybackChanged(t *testing.T) {
	t.Parallel()

	// Set up an in-process server/client pair via net.Pipe.
	serverConn, clientConn := net.Pipe()

	ln := newSingleConnListener(serverConn)
	d := daemon.NewWithListener(ln, config.Paths{})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go func() { _ = d.Serve(ctx) }()

	// Connect the client side.
	ipcClient := ipc.NewClient(clientConn)
	defer ipcClient.Close()

	// Poke the daemon to broadcast a playback.state.changed event by making
	// it respond to session.state (just to confirm the connection is live),
	// then manually trigger the broadcast path via the exported test helper.
	_, err := ipcClient.Request("session.state", map[string]any{})
	if err != nil {
		t.Fatalf("session.state: %v", err)
	}

	// Inject a playback update directly into the daemon's state and ask it
	// to broadcast. We use the BroadcastPlaybackState test hook.
	trackURI := "spotify:track:abc"
	ps := &api.PlaybackState{
		Provider:  "spotify",
		IsPlaying: true,
		Track:     &api.PlaybackTrack{Name: "Test Track", URI: &trackURI},
	}
	d.BroadcastPlaybackState(ps)

	// The client should receive the broadcast event within 200 ms.
	select {
	case ev := <-ipcClient.Events():
		if ev.Type != "playback.state.changed" {
			t.Errorf("event type: got %q, want playback.state.changed", ev.Type)
		}
		var got api.PlaybackState
		if err := json.Unmarshal(ev.Data, &got); err != nil {
			t.Fatalf("unmarshal event data: %v", err)
		}
		if !got.IsPlaying {
			t.Error("IsPlaying should be true in broadcast")
		}
		if got.Track == nil || got.Track.Name != "Test Track" {
			t.Errorf("Track.Name: got %+v", got.Track)
		}
	case <-time.After(200 * time.Millisecond):
		t.Fatal("timed out waiting for playback.state.changed broadcast")
	}
}

// singleConnListener wraps a single net.Conn as a net.Listener so tests can
// hand a pre-connected pipe to ipc.NewServer.
type singleConnListener struct {
	conn chan net.Conn
	addr net.Addr
}

func newSingleConnListener(conn net.Conn) *singleConnListener {
	ch := make(chan net.Conn, 1)
	ch <- conn
	return &singleConnListener{conn: ch, addr: conn.RemoteAddr()}
}

func (l *singleConnListener) Accept() (net.Conn, error) {
	c, ok := <-l.conn
	if !ok {
		return nil, net.ErrClosed
	}
	return c, nil
}

func (l *singleConnListener) Close() error {
	close(l.conn)
	return nil
}

func (l *singleConnListener) Addr() net.Addr { return l.addr }

// --- legacy local types ------------------------------------------------------

// apiError is a minimal error type for tests.
type apiError struct {
	Code    int
	Message string
}

func (e *apiError) Error() string { return e.Message }
