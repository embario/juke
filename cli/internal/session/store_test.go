package session_test

import (
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"github.com/embario/juke/cli/internal/session"
)

// TestSessionRoundTrip verifies Save → Load returns identical data.
func TestSessionRoundTrip(t *testing.T) {
	t.Parallel()
	path := filepath.Join(t.TempDir(), "session.json")

	want := session.Session{
		Username: "melodyqueen",
		Token:    "abc123tok",
		SavedAt:  time.Date(2026, 1, 2, 3, 4, 5, 0, time.UTC),
	}

	if err := session.Save(path, want); err != nil {
		t.Fatalf("Save: %v", err)
	}

	got, err := session.Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if got == nil {
		t.Fatal("Load returned nil for existing file")
	}
	if got.Username != want.Username {
		t.Errorf("Username: got %q, want %q", got.Username, want.Username)
	}
	if got.Token != want.Token {
		t.Errorf("Token: got %q, want %q", got.Token, want.Token)
	}
	if !got.SavedAt.Equal(want.SavedAt) {
		t.Errorf("SavedAt: got %v, want %v", got.SavedAt, want.SavedAt)
	}
}

// TestSessionMissing verifies that loading a nonexistent file returns nil, nil.
func TestSessionMissing(t *testing.T) {
	t.Parallel()
	path := filepath.Join(t.TempDir(), "nosession.json")

	got, err := session.Load(path)
	if err != nil {
		t.Fatalf("Load nonexistent: %v", err)
	}
	if got != nil {
		t.Errorf("expected nil session for missing file, got %+v", got)
	}
}

// TestSessionSavePerms verifies that Save creates the file with mode 0600.
// Skipped on Windows where Unix permission bits don't apply.
func TestSessionSavePerms(t *testing.T) {
	t.Parallel()
	if runtime.GOOS == "windows" {
		t.Skip("Unix permission bits do not apply on Windows")
	}

	path := filepath.Join(t.TempDir(), "session.json")
	s := session.Session{Username: "u", Token: "t", SavedAt: time.Now()}
	if err := session.Save(path, s); err != nil {
		t.Fatalf("Save: %v", err)
	}

	info, err := getFileInfo(path)
	if err != nil {
		t.Fatalf("stat: %v", err)
	}
	// Mask to permission bits only.
	mode := info.Mode().Perm()
	if mode != 0o600 {
		t.Errorf("file mode: got %04o, want 0600", mode)
	}
}

// TestSessionDelete verifies Delete removes the file and is idempotent.
func TestSessionDelete(t *testing.T) {
	t.Parallel()
	path := filepath.Join(t.TempDir(), "session.json")
	s := session.Session{Username: "u", Token: "t", SavedAt: time.Now()}
	if err := session.Save(path, s); err != nil {
		t.Fatal(err)
	}
	if err := session.Delete(path); err != nil {
		t.Fatalf("Delete: %v", err)
	}
	// Second delete on missing file must not error.
	if err := session.Delete(path); err != nil {
		t.Errorf("Delete (idempotent): %v", err)
	}
	// Load after delete returns nil.
	got, err := session.Load(path)
	if err != nil {
		t.Fatalf("Load after delete: %v", err)
	}
	if got != nil {
		t.Errorf("expected nil after delete, got %+v", got)
	}
}
