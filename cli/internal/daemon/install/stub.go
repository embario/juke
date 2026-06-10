// Package install contains per-OS service unit writers for "juked install".
// All implementations are TODO stubs; Phase 1 only scaffolds the cobra
// subcommand and this package.
package install

import "errors"

// ErrNotImplemented is returned by all Install functions until they are written.
var ErrNotImplemented = errors.New("service installation not yet implemented")

// Install writes the platform-appropriate service unit file and prints
// instructions for enabling it. Not yet implemented.
func Install() error { return ErrNotImplemented }

// Uninstall removes the service unit file. Not yet implemented.
func Uninstall() error { return ErrNotImplemented }
