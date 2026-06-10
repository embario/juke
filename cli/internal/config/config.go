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
	// e.g. "https://juke.example.com" or "http://127.0.0.1:8000"
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

// Load reads a TOML config file from path.
// If the file does not exist, Load returns defaults with no error.
// Any other I/O or parse error is returned.
func Load(path string) (Config, error) {
	cfg := defaults()
	_, err := toml.DecodeFile(path, &cfg)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return cfg, nil
		}
		return Config{}, fmt.Errorf("config: decode %s: %w", path, err)
	}
	return cfg, nil
}
