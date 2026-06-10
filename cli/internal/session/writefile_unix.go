//go:build !windows

package session

import "os"

// writeFile writes data to path with mode 0600 on Unix.
// Uses os.OpenFile so the perm is set atomically on create; a pre-existing
// file at path is truncated and overwritten.
func writeFile(path string, data []byte) error {
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o600)
	if err != nil {
		return err
	}
	if _, err := f.Write(data); err != nil {
		f.Close()
		return err
	}
	return f.Close()
}
