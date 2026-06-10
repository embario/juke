//go:build windows

// Windows named-pipe support is a Phase 1b deliverable.
// The stubs here allow the package to compile on windows/amd64 while making
// the limitation explicit at runtime.
//
// TODO(phase-1b): replace with github.com/Microsoft/go-winio named pipes.
// Pipe path: \\.\pipe\juke
package ipc

import (
	"errors"
	"net"
)

// ErrAlreadyRunning mirrors the Unix declaration so callers are platform-agnostic.
var ErrAlreadyRunning = errors.New("ipc: daemon already running on socket")

var errNotImplemented = errors.New("ipc: Windows named-pipe transport not yet implemented (Phase 1b)")

// SocketPath returns the Windows named-pipe path.
func SocketPath() string { return `\\.\pipe\juke` }

// Listen is not yet implemented on Windows.
func Listen(path string) (net.Listener, error) { return nil, errNotImplemented }

// Dial is not yet implemented on Windows.
func Dial(path string) (net.Conn, error) { return nil, errNotImplemented }
