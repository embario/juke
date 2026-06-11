package daemon

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	"github.com/embario/juke/cli/internal/api"
	"github.com/embario/juke/cli/internal/config"
	"github.com/embario/juke/cli/internal/ipc"
	"github.com/embario/juke/cli/internal/session"
	"github.com/embario/juke/cli/internal/transport"
)

// Daemon is the juked process: it owns the IPC server, session state, and
// the backend transport (polling in Phase 1b; WebSocket in Phase 3).
type Daemon struct {
	cfg   config.Config
	paths config.Paths
	state *State
	api   *api.Client

	// server is set by Run (or NewWithListener for tests).
	server *ipc.Server

	// transport fields — all guarded by transportOnce / transportCtx.
	transport       *transport.Manager
	transportOnce   sync.Once
	transportCtx    context.Context
	transportCancel context.CancelFunc
	transportUpdates chan *api.PlaybackState // shared with drain goroutine
}

// New creates a Daemon. It loads config from the platform config path,
// restores any persisted session, and prepares the API client.
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

	return &Daemon{
		cfg:   cfg,
		paths: paths,
		state: state,
		api:   apiClient,
	}, nil
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

	// Transport manager — broadcast is wired now that the server exists.
	d.transport = transport.NewManager(d.api, d.pollInterval(), d.server.Broadcast)
	d.transportCtx, d.transportCancel = context.WithCancel(ctx)

	// Shared updates channel. The drain goroutine caches state and broadcasts
	// playback.state.changed to all connected TUI clients.
	updates := make(chan *api.PlaybackState, 16)
	d.transportUpdates = updates
	go d.drainUpdates(updates)

	// Start transport immediately when a session is already present (daemon
	// restarted while the user was logged in). Don't poll with an empty token;
	// every tick would produce a 401 and generate log noise.
	if d.state.Token() != "" {
		d.doStartTransport()
	}

	fmt.Fprintf(os.Stderr, "juked: listening on %s\n", d.paths.Socket)
	err = d.server.Accept(ctx)
	d.transportCancel()
	return err
}

// drainUpdates reads *api.PlaybackState values from the transport's updates
// channel, caches them in daemon state, and broadcasts playback.state.changed.
func (d *Daemon) drainUpdates(updates <-chan *api.PlaybackState) {
	for s := range updates {
		d.state.SetPlaybackState(s)
		ev, err := ipc.MsgEvent("playback.state.changed", s)
		if err == nil {
			d.server.Broadcast(ev)
		}
	}
}

// doStartTransport starts transport.Manager in a goroutine. Idempotent:
// the sync.Once guard ensures at most one transport runs per Daemon lifetime.
func (d *Daemon) doStartTransport() {
	d.transportOnce.Do(func() {
		go d.transport.Start(d.transportCtx, d.transportUpdates)
	})
}

// startTransport is called from dispatch after a successful login. It is
// safe to call before or after Run's early-start check; the once guard
// ensures only one transport goroutine is ever created.
func (d *Daemon) startTransport() {
	if d.transport != nil {
		d.doStartTransport()
	}
}

// pollInterval returns the configured poll interval, defaulting to 10 s.
func (d *Daemon) pollInterval() time.Duration {
	secs := d.cfg.Transport.PollIntervalSeconds
	if secs <= 0 {
		secs = 10
	}
	return time.Duration(secs) * time.Second
}

// dispatch routes an incoming IPC message to the correct handler.
func (d *Daemon) dispatch(req ipc.Message) *ipc.Message {
	sessPath := filepath.Join(d.paths.Data, "session.json")

	switch req.Type {
	case "session.state":
		return HandleSessionState(req, d.state)

	case "session.login":
		resp := HandleSessionLogin(req, d.state, sessPath, d.apiLogin, d.server.Broadcast)
		// Arm the transport after the first successful login so polling begins
		// as soon as the token is known.
		if resp != nil && resp.Type == "ok" {
			d.startTransport()
		}
		return resp

	case "session.logout":
		return HandleSessionLogout(req, d.state, sessPath, d.apiLogout, d.server.Broadcast)

	case "playback.state":
		return HandlePlaybackState(req, d.state)

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
	// Keep the API client token in sync for subsequent requests (e.g. polling).
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

// BroadcastPlaybackState updates the cached playback state and broadcasts a
// playback.state.changed event to all connected clients. It replicates the
// inner loop of drainUpdates so tests can inject synthetic transport updates
// without running the full transport goroutine.
func (d *Daemon) BroadcastPlaybackState(ps *api.PlaybackState) {
	d.state.SetPlaybackState(ps)
	ev, err := ipc.MsgEvent("playback.state.changed", ps)
	if err == nil {
		d.server.Broadcast(ev)
	}
}
