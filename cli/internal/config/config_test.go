package config_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/embario/juke/cli/internal/config"
)

// clearBackendEnv clears both backend URL env vars for the duration of a test.
// Prevents ambient BACKEND_URL (sourced from .env) from polluting defaults tests.
// Tests calling this must NOT call t.Parallel() — t.Setenv is incompatible
// with parallel tests because env vars are process-global state.
func clearBackendEnv(t *testing.T) {
	t.Helper()
	t.Setenv("BACKEND_URL", "")
	t.Setenv("JUKE_BACKEND_URL", "")
}

// TestConfigDefaults verifies that loading a nonexistent file returns sane
// defaults and no error.
func TestConfigDefaults(t *testing.T) {
	// Not parallel: uses t.Setenv via clearBackendEnv.
	clearBackendEnv(t)

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

// TestConfigEmptyPath verifies that an empty path behaves like a missing file.
func TestConfigEmptyPath(t *testing.T) {
	// Not parallel: uses t.Setenv via clearBackendEnv.
	clearBackendEnv(t)

	cfg, err := config.Load("")
	if err != nil {
		t.Fatalf("Load empty path: %v", err)
	}
	if cfg.Transport.PollIntervalSeconds != 10 {
		t.Errorf("PollIntervalSeconds: got %d, want 10", cfg.Transport.PollIntervalSeconds)
	}
}

// TestConfigLoad verifies round-trip for a valid TOML file.
func TestConfigLoad(t *testing.T) {
	// Not parallel: uses t.Setenv via clearBackendEnv.
	clearBackendEnv(t)

	dir := t.TempDir()
	path := filepath.Join(dir, "config.toml")

	content := `
backend_url = "http://127.0.0.1:8000"

[transport]
mode = "polling"
poll_interval_seconds = 5
`
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
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
	t.Parallel() // does not touch env vars

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

// TestConfigEnvOverridesFile verifies that BACKEND_URL overrides a value set
// in config.toml — env always wins over file.
func TestConfigEnvOverridesFile(t *testing.T) {
	// Not parallel: uses t.Setenv.
	t.Setenv("BACKEND_URL", "http://env-override:9000")
	t.Setenv("JUKE_BACKEND_URL", "")

	dir := t.TempDir()
	path := filepath.Join(dir, "config.toml")
	if err := os.WriteFile(path, []byte(`backend_url = "http://file-value:8000"`), 0o644); err != nil {
		t.Fatal(err)
	}

	cfg, err := config.Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.BackendURL != "http://env-override:9000" {
		t.Errorf("BackendURL: got %q, want env value", cfg.BackendURL)
	}
}

// TestConfigJukeEnvTakesPriority verifies that JUKE_BACKEND_URL wins over
// the shared BACKEND_URL env var.
func TestConfigJukeEnvTakesPriority(t *testing.T) {
	// Not parallel: uses t.Setenv.
	t.Setenv("BACKEND_URL", "http://shared:8000")
	t.Setenv("JUKE_BACKEND_URL", "http://cli-specific:9001")

	cfg, err := config.Load("")
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.BackendURL != "http://cli-specific:9001" {
		t.Errorf("BackendURL: got %q, want JUKE_BACKEND_URL value", cfg.BackendURL)
	}
}

// TestConfigEnvNoFile verifies that env overrides work even with no config
// file — the daemon can be configured entirely through the environment.
func TestConfigEnvNoFile(t *testing.T) {
	// Not parallel: uses t.Setenv.
	t.Setenv("BACKEND_URL", "http://env-only:8001")
	t.Setenv("JUKE_BACKEND_URL", "")

	cfg, err := config.Load("")
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.BackendURL != "http://env-only:8001" {
		t.Errorf("BackendURL: got %q, want http://env-only:8001", cfg.BackendURL)
	}
	// Transport defaults are still applied when no file is present.
	if cfg.Transport.PollIntervalSeconds != 10 {
		t.Errorf("PollIntervalSeconds: got %d, want 10", cfg.Transport.PollIntervalSeconds)
	}
}

// TestFindConfigJUKE_CONFIG verifies $JUKE_CONFIG is used when set.
func TestFindConfigJUKE_CONFIG(t *testing.T) {
	// Not parallel: uses t.Setenv.
	dir := t.TempDir()
	target := filepath.Join(dir, "my-config.toml")
	if err := os.WriteFile(target, []byte(`backend_url = "http://explicit:1234"`), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("JUKE_CONFIG", target)

	got := config.FindConfigPath()
	if got != target {
		t.Errorf("FindConfigPath: got %q, want %q", got, target)
	}
}
