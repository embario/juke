package daemon

import (
	"encoding/json"
	"fmt"

	"github.com/embario/juke/cli/internal/ipc"
	"github.com/embario/juke/cli/internal/session"
)

// loginRequest is the expected payload for session.login.
type loginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// HandleSessionState returns the current session snapshot.
func HandleSessionState(req ipc.Message, state *State) *ipc.Message {
	snap := state.Session()
	resp, err := ipc.OKResponse(req, snap)
	if err != nil {
		e := ipc.ErrorResponse(req, "internal", err.Error())
		return &e
	}
	return &resp
}

// HandleSessionLogin authenticates with the backend, persists the token, and
// broadcasts a session.changed event.
// apiLogin is a function to allow injection in tests.
func HandleSessionLogin(
	req ipc.Message,
	state *State,
	sessPath string,
	apiLogin func(username, password string) (token string, err error),
	broadcast func(ipc.Message),
) *ipc.Message {
	var lr loginRequest
	if err := json.Unmarshal(req.Data, &lr); err != nil {
		e := ipc.ErrorResponse(req, "bad_request", "invalid login payload")
		return &e
	}
	if lr.Username == "" || lr.Password == "" {
		e := ipc.ErrorResponse(req, "bad_request", "username and password are required")
		return &e
	}

	token, err := apiLogin(lr.Username, lr.Password)
	if err != nil {
		e := ipc.ErrorResponse(req, "auth_failed", err.Error())
		return &e
	}

	state.SetSession(lr.Username, token)

	if saveErr := session.Save(sessPath, session.Session{
		Username: lr.Username,
		Token:    token,
	}); saveErr != nil {
		// Non-fatal: daemon is authenticated in-memory even if disk write fails.
		fmt.Printf("daemon: warning: could not persist session: %v\n", saveErr)
	}

	snap := state.Session()
	ev, err := ipc.MsgEvent("session.changed", snap)
	if err == nil {
		broadcast(ev)
	}

	resp, err := ipc.OKResponse(req, snap)
	if err != nil {
		e := ipc.ErrorResponse(req, "internal", err.Error())
		return &e
	}
	return &resp
}

// HandlePlaybackState returns the cached playback state without making a
// backend round-trip. Returns null data when no state is cached yet.
func HandlePlaybackState(req ipc.Message, state *State) *ipc.Message {
	ps := state.PlaybackState() // nil is valid — nothing playing
	resp, err := ipc.OKResponse(req, ps)
	if err != nil {
		e := ipc.ErrorResponse(req, "internal", err.Error())
		return &e
	}
	return &resp
}

// HandleSessionLogout clears the session, removes the session file, and
// broadcasts a session.changed event.
// apiLogout is called best-effort; its error does not prevent local cleanup.
func HandleSessionLogout(
	req ipc.Message,
	state *State,
	sessPath string,
	apiLogout func() error,
	broadcast func(ipc.Message),
) *ipc.Message {
	_ = apiLogout() // best-effort; ignore error

	state.ClearSession()
	_ = session.Delete(sessPath) // ignore error

	snap := state.Session() // authenticated == false
	ev, err := ipc.MsgEvent("session.changed", snap)
	if err == nil {
		broadcast(ev)
	}

	resp, err := ipc.OKResponse(req, snap)
	if err != nil {
		e := ipc.ErrorResponse(req, "internal", err.Error())
		return &e
	}
	return &resp
}
