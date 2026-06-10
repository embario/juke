//go:build windows

package session

import "os"

// writeFile writes data to path on Windows. The file inherits the ACLs of its
// parent directory (%APPDATA%\Juke), which is already user-scoped.
// Unix-style mode bits don't map to Windows ACLs; this is accepted as
// best-effort for the platform.
func writeFile(path string, data []byte) error {
	return os.WriteFile(path, data, 0o600)
}
