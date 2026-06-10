// Package tui is the bubbletea application for the juke TUI client.
// Phase 1 renders only the session status screen: not-logged-in + login prompt,
// or "logged in as <username>". Playback panes, nav, and search land in Phase 3.
package tui

import (
	"encoding/json"
	"fmt"

	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"

	"github.com/embario/juke/cli/internal/daemon"
	"github.com/embario/juke/cli/internal/ipc"
)

// ---- messages ---------------------------------------------------------------

// ipcConnectedMsg is delivered once the IPC client is connected and the initial
// session.state response has been read.
type ipcConnectedMsg struct {
	client *ipc.Client
	snap   daemon.SessionSnapshot
}

// ipcEventMsg carries a server-pushed event (session.changed, etc.).
type ipcEventMsg struct{ msg ipc.Message }

// ipcErrMsg is sent when the IPC connection fails or drops.
type ipcErrMsg struct{ err error }

// loginResultMsg carries the outcome of a session.login request.
type loginResultMsg struct {
	snap daemon.SessionSnapshot
	err  error
}

// ---- model ------------------------------------------------------------------

// field indices for the login form
const (
	fieldUsername = 0
	fieldPassword = 1
)

// Model is the root bubbletea model. Intentionally flat for Phase 1.
type Model struct {
	client     *ipc.Client
	socketPath string

	// connection
	connected bool
	connErr   string

	// session
	snap daemon.SessionSnapshot

	// login form
	inputs     [2]textinput.Model
	focusIndex int
	loginErr   string
	submitting bool
}

// New creates the root Model. socketPath is the IPC socket to connect to.
func New(socketPath string) Model {
	u := textinput.New()
	u.Placeholder = "username"
	u.Focus()
	u.CharLimit = 128

	p := textinput.New()
	p.Placeholder = "password"
	p.EchoMode = textinput.EchoPassword
	p.CharLimit = 128

	return Model{
		socketPath: socketPath,
		inputs:     [2]textinput.Model{u, p},
	}
}

// Init connects to the IPC socket and fetches session state.
// Runs as a tea.Cmd (goroutine) so Update is never blocked.
func (m Model) Init() tea.Cmd {
	return connectAndFetch(m.socketPath)
}

// Update handles all incoming messages.
func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {

	case ipcConnectedMsg:
		m.client = msg.client
		m.connected = true
		m.snap = msg.snap
		return m, waitForEvent(m.client)

	case ipcErrMsg:
		m.connErr = msg.err.Error()
		return m, nil

	case ipcEventMsg:
		if msg.msg.Type == "session.changed" {
			var snap daemon.SessionSnapshot
			_ = json.Unmarshal(msg.msg.Data, &snap)
			m.snap = snap
		}
		// Re-arm: wait for the next event.
		return m, waitForEvent(m.client)

	case loginResultMsg:
		m.submitting = false
		if msg.err != nil {
			m.loginErr = msg.err.Error()
			return m, nil
		}
		m.snap = msg.snap
		m.loginErr = ""
		return m, nil

	case tea.KeyMsg:
		return m.handleKey(msg)
	}
	return m, nil
}

func (m Model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	// Always quit on Ctrl+C.
	if msg.Type == tea.KeyCtrlC {
		return m, tea.Quit
	}

	// Logged-in view: q quits.
	if m.snap.Authenticated {
		if msg.Type == tea.KeyRunes && string(msg.Runes) == "q" {
			return m, tea.Quit
		}
		return m, nil
	}

	// Login form key handling.
	if !m.connected || m.submitting {
		return m, nil
	}

	switch msg.Type {
	case tea.KeyTab, tea.KeyShiftTab:
		m.focusIndex = (m.focusIndex + 1) % 2
		m.inputs[0].Blur()
		m.inputs[1].Blur()
		m.inputs[m.focusIndex].Focus()
		return m, nil

	case tea.KeyEnter:
		if m.focusIndex == fieldUsername {
			// Advance to password field.
			m.focusIndex = fieldPassword
			m.inputs[0].Blur()
			m.inputs[1].Focus()
			return m, nil
		}
		// Submit from password field.
		username := m.inputs[fieldUsername].Value()
		password := m.inputs[fieldPassword].Value()
		if username == "" || password == "" {
			m.loginErr = "username and password are required"
			return m, nil
		}
		m.submitting = true
		m.loginErr = ""
		return m, sendLogin(m.client, username, password)
	}

	// Forward key events to the focused input.
	var cmd tea.Cmd
	m.inputs[m.focusIndex], cmd = m.inputs[m.focusIndex].Update(msg)
	return m, cmd
}

// View renders the current state as plain text.
func (m Model) View() string {
	if m.connErr != "" {
		return fmt.Sprintf(
			"juke: cannot connect to daemon\n  %s\n\nStart the daemon first:\n  juked --foreground\n\nCtrl+C to quit.\n",
			m.connErr,
		)
	}
	if !m.connected {
		return "juke: connecting…\n"
	}
	if m.snap.Authenticated {
		return fmt.Sprintf("juke — ✓ logged in as %s\n\nPress q or Ctrl+C to quit.\n", m.snap.Username)
	}

	s := "juke — log in\n\n"
	s += fmt.Sprintf("  username  %s\n", m.inputs[fieldUsername].View())
	s += fmt.Sprintf("  password  %s\n", m.inputs[fieldPassword].View())
	s += "\n  Tab · Enter to submit · Ctrl+C to quit\n"
	if m.loginErr != "" {
		s += fmt.Sprintf("\n  ✗ %s\n", m.loginErr)
	}
	if m.submitting {
		s += "\n  logging in…\n"
	}
	return s
}

// ---- commands ---------------------------------------------------------------

// connectAndFetch dials the IPC socket, sends session.state, and returns
// the connection + snapshot as a single message.
func connectAndFetch(socketPath string) tea.Cmd {
	return func() tea.Msg {
		client, err := ipc.DialClient(socketPath)
		if err != nil {
			return ipcErrMsg{fmt.Errorf("connect: %w", err)}
		}
		resp, err := client.Request("session.state", map[string]any{})
		if err != nil {
			client.Close()
			return ipcErrMsg{fmt.Errorf("session.state: %w", err)}
		}
		var snap daemon.SessionSnapshot
		if err := json.Unmarshal(resp.Data, &snap); err != nil {
			client.Close()
			return ipcErrMsg{fmt.Errorf("decode session: %w", err)}
		}
		return ipcConnectedMsg{client: client, snap: snap}
	}
}

// waitForEvent blocks until one server-pushed event arrives on the client's
// Events channel, then delivers it as a tea.Msg.
// The TUI re-arms by calling waitForEvent again from Update.
func waitForEvent(client *ipc.Client) tea.Cmd {
	return func() tea.Msg {
		ev, ok := <-client.Events()
		if !ok {
			return ipcErrMsg{fmt.Errorf("daemon disconnected")}
		}
		return ipcEventMsg{ev}
	}
}

// sendLogin sends a session.login IPC request.
func sendLogin(client *ipc.Client, username, password string) tea.Cmd {
	return func() tea.Msg {
		resp, err := client.Request("session.login", map[string]string{
			"username": username,
			"password": password,
		})
		if err != nil {
			return loginResultMsg{err: err}
		}
		if resp.Type == "error" {
			var errBody struct {
				Message string `json:"message"`
			}
			_ = json.Unmarshal(resp.Data, &errBody)
			return loginResultMsg{err: fmt.Errorf("%s", errBody.Message)}
		}
		var snap daemon.SessionSnapshot
		_ = json.Unmarshal(resp.Data, &snap)
		return loginResultMsg{snap: snap}
	}
}
