// Package config handles TOML configuration loading and platform path resolution.
package config

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
)

// Paths holds the resolved filesystem locations for all Juke CLI data.
type Paths struct {
	// Config is the path to config.toml.
	Config string
	// Data is the directory for persistent data (session.json lives here).
	Data string
	// Socket is the IPC socket path (platform-specific; see ipc package).
	Socket string
}

// ResolvePaths returns platform-appropriate paths following XDG on Linux,
// ~/Library/Application Support/Juke on macOS, and %APPDATA%\Juke on Windows.
func ResolvePaths() (Paths, error) {
	switch runtime.GOOS {
	case "darwin":
		return darwinPaths()
	case "windows":
		return windowsPaths()
	default:
		return xdgPaths()
	}
}

func darwinPaths() (Paths, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return Paths{}, fmt.Errorf("config: resolve home: %w", err)
	}
	base := filepath.Join(home, "Library", "Application Support", "Juke")
	return Paths{
		Config: filepath.Join(base, "config.toml"),
		Data:   base,
		Socket: filepath.Join(base, "juke.sock"),
	}, nil
}

func windowsPaths() (Paths, error) {
	appdata := os.Getenv("APPDATA")
	if appdata == "" {
		return Paths{}, fmt.Errorf("config: APPDATA not set")
	}
	base := filepath.Join(appdata, "Juke")
	return Paths{
		Config: filepath.Join(base, "config.toml"),
		Data:   base,
		Socket: `\\.\pipe\juke`,
	}, nil
}

func xdgPaths() (Paths, error) {
	cfgDir := os.Getenv("XDG_CONFIG_HOME")
	if cfgDir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return Paths{}, fmt.Errorf("config: resolve home: %w", err)
		}
		cfgDir = filepath.Join(home, ".config")
	}

	dataDir := os.Getenv("XDG_DATA_HOME")
	if dataDir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return Paths{}, fmt.Errorf("config: resolve home: %w", err)
		}
		dataDir = filepath.Join(home, ".local", "share")
	}

	rtDir := os.Getenv("XDG_RUNTIME_DIR")
	var sockPath string
	if rtDir != "" {
		sockPath = filepath.Join(rtDir, "juke.sock")
	} else {
		sockPath = fmt.Sprintf("/tmp/juke-%d.sock", os.Getuid())
	}

	return Paths{
		Config: filepath.Join(cfgDir, "juke", "config.toml"),
		Data:   filepath.Join(dataDir, "juke"),
		Socket: sockPath,
	}, nil
}
