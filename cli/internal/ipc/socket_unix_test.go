//go:build !windows

package ipc_test

import (
	"net"
	"os"
	"path/filepath"
	"testing"

	"github.com/embario/juke/cli/internal/ipc"
)

// TestStaleSocketCleanup verifies that Listen removes a stale socket file
// (left by a crashed daemon) and rebinds successfully.
//
// Note: Go's net.UnixListener.Close() removes the socket file automatically,
// so we cannot use net.Listen + Close to simulate a crash. Instead we use the
// raw syscall layer, which leaves the file on disk after the FD is closed —
// exactly what happens when a daemon is killed -9.
func TestStaleSocketCleanup(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	sockPath := filepath.Join(dir, "juke.sock")

	// Create socket file via raw syscall and immediately close the FD.
	// The file stays on disk (no listener registered = no auto-cleanup).
	if err := createStaleSocket(sockPath); err != nil {
		t.Fatalf("setup: create stale socket: %v", err)
	}

	// Verify the stale file exists.
	if _, err := os.Stat(sockPath); err != nil {
		t.Fatalf("setup: stale socket file missing: %v", err)
	}

	// Listen should clean up and rebind without error.
	ln, err := ipc.Listen(sockPath)
	if err != nil {
		t.Fatalf("Listen after stale socket: %v", err)
	}
	defer ln.Close()

	// Verify we can actually connect to the new listener.
	conn, err := net.Dial("unix", sockPath)
	if err != nil {
		t.Fatalf("Dial after rebind: %v", err)
	}
	conn.Close()
}

// TestListenErrAlreadyRunning verifies that Listen on an active socket returns
// ErrAlreadyRunning rather than stealing the port.
func TestListenErrAlreadyRunning(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	sockPath := filepath.Join(dir, "juke.sock")

	ln, err := ipc.Listen(sockPath)
	if err != nil {
		t.Fatalf("first Listen: %v", err)
	}
	defer ln.Close()

	_, err = ipc.Listen(sockPath)
	if err != ipc.ErrAlreadyRunning {
		t.Errorf("second Listen: got %v, want ErrAlreadyRunning", err)
	}
}
