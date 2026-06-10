package daemon

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	"github.com/embario/juke/cli/internal/api"
	"github.com/embario/juke/cli/internal/config"
	"github.com/embario/juke/cli/internal/ipc"
	"github.com/embario/juke/cli/internal/session"
)

// Daemon is the juked process: it owns the IPC server, session state, and
// (in later phases) the backend transport.
type Daemon struct {
	cfg    config.Config
	paths  config.Paths
	state  *State
	server *ipc.Server
	api    *api.Client
}

// New creates a Daemon. It loads config from the platform config path,
// restores any persisted session, and prepares the IPC server.
// Call Run to start serving.
func New(paths config.Paths) (*Daemon, error) {
	cfg, err := config.Load(paths.Config)
	if err != nil {
		return nil, fmt.Errorf("daemon: load config: %w", err)
	}

	state := &State{}

	// Restore session from disk (user stays logged in across restarts).
	sessFile := filepath.Join(paths.Data, "session.json")
	if sess, err := session.Load(sessFile); err == nil && sess != nil {
		state.SetSession(sess.Username, sess.Token)
	}

	apiClient := api.New(cfg.BackendURL)
	if state.Token() != "" {
		apiClient.SetToken(state.Token())
	}

	d := &Daemon{
		cfg:   cfg,
		paths: paths,
		state: state,
		api:   apiClient,
	}

	return d, nil
}

// Run starts the IPC server and blocks until the context is cancelled or
// SIGINT/SIGTERM is received. The socket path is written to stderr on startup.
func (d *Daemon) Run(ctx context.Context) error {
	ctx, cancel := signal.NotifyContext(ctx, syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	ln, err := ipc.Listen(d.paths.Socket)
	if err != nil {
		if errors.Is(err, ipc.ErrAlreadyRunning) {
			return fmt.Errorf("daemon: %w", err)
		}
		return fmt.Errorf("daemon: bind socket: %w", err)
	}

	d.server = ipc.NewServer(ln, d.dispatch)
	fmt.Fprintf(os.Stderr, "juked: listening on %s\n", d.paths.Socket)

	return d.server.Accept(ctx)
}

// dispatch routes an incoming IPC message to the correct handler.
func (d *Daemon) dispatch(req ipc.Message) *ipc.Message {
	sessPath := filepath.Join(d.paths.Data, "session.json")

	switch req.Type {
	case "session.state":
		return HandleSessionState(req, d.state)

	case "session.login":
		return HandleSessionLogin(req, d.state, sessPath, d.apiLogin, d.server.Broadcast)

	case "session.logout":
		return HandleSessionLogout(req, d.state, sessPath, d.apiLogout, d.server.Broadcast)

	default:
		e := ipc.ErrorResponse(req, "unknown_type", fmt.Sprintf("unknown message type: %q", req.Type))
		return &e
	}
}

// apiLogin delegates to the real HTTP client.
func (d *Daemon) apiLogin(username, password string) (string, error) {
	if d.cfg.BackendURL == "" {
		return "", fmt.Errorf("backend_url not set in config.toml")
	}
	tok, err := d.api.Login(username, password)
	if err != nil {
		return "", err
	}
	// Keep client token in sync for subsequent requests.
	d.api.SetToken(tok)
	return tok, nil
}

// apiLogout delegates to the real HTTP client. Best-effort.
func (d *Daemon) apiLogout() error {
	err := d.api.Logout()
	d.api.ClearToken()
	return err
}

// NewWithListener creates a Daemon bound to an already-open listener. Used in
// tests to avoid filesystem socket creation.
func NewWithListener(ln net.Listener, paths config.Paths) *Daemon {
	state := &State{}
	d := &Daemon{
		cfg:   config.Config{},
		paths: paths,
		state: state,
		api:   api.New(""),
	}
	d.server = ipc.NewServer(ln, d.dispatch)
	return d
}

// Serve runs the IPC accept loop using an existing listener (test helper).
func (d *Daemon) Serve(ctx context.Context) error {
	return d.server.Accept(ctx)
}
