// Package session manages the on-disk session file (session.json).
// The file holds the auth token and is written mode 0600 on Unix.
// Only the daemon reads and writes this file; the TUI always asks the daemon.
package session

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// Session is the persisted session state.
type Session struct {
	Username string    `json:"username"`
	Token    string    `json:"token"`
	SavedAt  time.Time `json:"saved_at"`
}

// Load reads session.json from path. Returns nil, nil if the file does not
// exist (i.e. the user is not logged in).
func Load(path string) (*Session, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, nil
		}
		return nil, fmt.Errorf("session: read %s: %w", path, err)
	}
	var s Session
	if err := json.Unmarshal(data, &s); err != nil {
		return nil, fmt.Errorf("session: decode %s: %w", path, err)
	}
	return &s, nil
}

// Save writes s to path as JSON, creating parent directories as needed.
// On Unix the file is created with mode 0600. On Windows the file inherits
// the ACLs of %APPDATA%\Juke, which is already user-scoped.
func Save(path string, s Session) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("session: mkdir: %w", err)
	}
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return fmt.Errorf("session: marshal: %w", err)
	}
	return writeFile(path, data) // platform-specific perm logic below
}

// Delete removes the session file. Safe to call when the file does not exist.
func Delete(path string) error {
	err := os.Remove(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return err
}
