//go:build !windows

package ipc

import (
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"runtime"
)

// ErrAlreadyRunning is returned when a live daemon is already bound to the
// socket path. The caller should connect as a client instead.
var ErrAlreadyRunning = errors.New("ipc: daemon already running on socket")

// SocketPath returns the platform-appropriate Unix domain socket path.
//
//   - Linux: $XDG_RUNTIME_DIR/juke.sock, fallback /tmp/juke-<uid>.sock
//   - macOS: ~/Library/Application Support/Juke/juke.sock
func SocketPath() string {
	switch runtime.GOOS {
	case "darwin":
		home, err := os.UserHomeDir()
		if err != nil {
			return "/tmp/juke.sock"
		}
		return filepath.Join(home, "Library", "Application Support", "Juke", "juke.sock")
	default: // linux and other Unix-likes
		if dir := os.Getenv("XDG_RUNTIME_DIR"); dir != "" {
			return filepath.Join(dir, "juke.sock")
		}
		return fmt.Sprintf("/tmp/juke-%d.sock", os.Getuid())
	}
}

// Listen creates a Unix domain socket listener at path. If a stale socket
// file exists (e.g. from a crashed daemon), it is removed and rebound.
// Returns ErrAlreadyRunning if a live daemon is already listening.
func Listen(path string) (net.Listener, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, fmt.Errorf("ipc: create socket dir: %w", err)
	}

	if _, err := os.Stat(path); err == nil {
		// Socket file exists. Probe it.
		conn, err := net.Dial("unix", path)
		if err == nil {
			// A live daemon answered — don't stomp on it.
			conn.Close()
			return nil, ErrAlreadyRunning
		}
		// Connection refused → stale file from a crashed daemon.
		if removeErr := os.Remove(path); removeErr != nil {
			return nil, fmt.Errorf("ipc: remove stale socket: %w", removeErr)
		}
	}

	ln, err := net.Listen("unix", path)
	if err != nil {
		return nil, fmt.Errorf("ipc: listen: %w", err)
	}
	return ln, nil
}

// Dial connects to the Unix domain socket at path.
func Dial(path string) (net.Conn, error) {
	conn, err := net.Dial("unix", path)
	if err != nil {
		return nil, fmt.Errorf("ipc: dial %s: %w", path, err)
	}
	return conn, nil
}
