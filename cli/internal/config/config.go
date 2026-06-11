package config

import (
	"errors"
	"fmt"
	"os"

	"github.com/BurntSushi/toml"
)

// Config holds all user-visible settings. Absent keys receive defaults when
// loading. Fields are intentionally minimal for Phase 1; extend in later phases.
type Config struct {
	// BackendURL is the base URL of the Juke backend (no trailing slash).
	// e.g. "https://juke.example.com" or "http://127.0.0.1:8001"
	//
	// Resolution order (highest to lowest priority):
	//   JUKE_BACKEND_URL env var  — CLI-specific override
	//   BACKEND_URL env var       — shared with the Docker Compose stack
	//   backend_url in config.toml
	//   "" (empty — daemon refuses to start without a valid URL)
	BackendURL string `toml:"backend_url"`

	Transport TransportConfig `toml:"transport"`
}

// TransportConfig controls how the daemon connects to the backend.
type TransportConfig struct {
	// Mode is "auto" (try WS, fall back to poll) or "polling" (force poll).
	// Phase 1 always polls regardless of this setting; WS lands in Phase 3.
	Mode string `toml:"mode"`

	// PollIntervalSeconds is how often the polling transport checks for state
	// changes. Defaults to 10.
	PollIntervalSeconds int `toml:"poll_interval_seconds"`
}

// defaults returns a Config populated with sane zero-config values.
func defaults() Config {
	return Config{
		Transport: TransportConfig{
			Mode:                "auto",
			PollIntervalSeconds: 10,
		},
	}
}

// Load reads a TOML config file from path and applies environment variable
// overrides on top. If path is empty or the file does not exist, Load returns
// defaults (plus any env overrides) with no error. Any other I/O or parse
// error is returned unchanged.
func Load(path string) (Config, error) {
	cfg := defaults()

	if path != "" {
		if _, err := toml.DecodeFile(path, &cfg); err != nil {
			if !errors.Is(err, os.ErrNotExist) {
				return Config{}, fmt.Errorf("config: decode %s: %w", path, err)
			}
			// File absent — continue with defaults.
		}
	}

	applyEnvOverrides(&cfg)
	return cfg, nil
}

// applyEnvOverrides applies environment variables on top of the values already
// loaded from config.toml (or defaults). Env vars always win so that the Docker
// Compose .env file is the single source of truth during development without
// requiring a manually maintained config file.
//
// Variables read:
//
//	BACKEND_URL        — shared with docker-compose; sets cfg.BackendURL.
//	JUKE_BACKEND_URL   — CLI-specific override; takes priority over BACKEND_URL.
func applyEnvOverrides(cfg *Config) {
	if v := os.Getenv("BACKEND_URL"); v != "" {
		cfg.BackendURL = v
	}
	// More specific CLI override wins over the shared stack variable.
	if v := os.Getenv("JUKE_BACKEND_URL"); v != "" {
		cfg.BackendURL = v
	}
}
