package config_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/embario/juke/cli/internal/config"
)

// TestConfigDefaults verifies that loading a nonexistent file returns sane
// defaults and no error.
func TestConfigDefaults(t *testing.T) {
	t.Parallel()
	path := filepath.Join(t.TempDir(), "config.toml")

	cfg, err := config.Load(path)
	if err != nil {
		t.Fatalf("Load nonexistent: %v", err)
	}
	if cfg.BackendURL != "" {
		t.Errorf("BackendURL default: got %q, want empty", cfg.BackendURL)
	}
	if cfg.Transport.PollIntervalSeconds != 10 {
		t.Errorf("PollIntervalSeconds default: got %d, want 10", cfg.Transport.PollIntervalSeconds)
	}
	if cfg.Transport.Mode != "auto" {
		t.Errorf("Mode default: got %q, want auto", cfg.Transport.Mode)
	}
}

// TestConfigLoad verifies round-trip for a valid TOML file.
func TestConfigLoad(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	path := filepath.Join(dir, "config.toml")

	toml := `
backend_url = "http://127.0.0.1:8000"

[transport]
mode = "polling"
poll_interval_seconds = 5
`
	if err := os.WriteFile(path, []byte(toml), 0o644); err != nil {
		t.Fatal(err)
	}

	cfg, err := config.Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.BackendURL != "http://127.0.0.1:8000" {
		t.Errorf("BackendURL: got %q", cfg.BackendURL)
	}
	if cfg.Transport.Mode != "polling" {
		t.Errorf("Mode: got %q", cfg.Transport.Mode)
	}
	if cfg.Transport.PollIntervalSeconds != 5 {
		t.Errorf("PollIntervalSeconds: got %d", cfg.Transport.PollIntervalSeconds)
	}
}

// TestConfigBadTOML verifies that a malformed TOML file returns an error.
func TestConfigBadTOML(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	path := filepath.Join(dir, "config.toml")
	if err := os.WriteFile(path, []byte("[not valid"), 0o644); err != nil {
		t.Fatal(err)
	}

	_, err := config.Load(path)
	if err == nil {
		t.Error("expected error for malformed TOML, got nil")
	}
}
