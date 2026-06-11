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
	// Config is the path to config.toml. Resolved by FindConfigPath; may be
	// empty when no file is found (Load will use defaults + env overrides).
	Config string
	// Data is the directory for persistent data (session.json lives here).
	// Always platform-specific — the session token must not follow the repo.
	Data string
	// Socket is the IPC socket path (platform-specific; see ipc package).
	Socket string
}

// FindConfigPath locates config.toml by searching in priority order:
//
//  1. $JUKE_CONFIG — explicit override, highest priority.
//  2. ./config.toml in the current working directory — works when running
//     with `go run ./cmd/juked` from the cli/ project directory.
//  3. config.toml in the binary's directory, then its parent directory —
//     handles installed binaries (cli/dist/juked finds cli/config.toml)
//     and symlinks (~/bin/juked resolved through the symlink first).
//
// Returns an empty string when no file is found; Load handles that gracefully
// by applying defaults and env overrides without reading any file.
func FindConfigPath() string {
	// 1. Explicit env var.
	if v := os.Getenv("JUKE_CONFIG"); v != "" {
		return v
	}

	// 2. Current working directory.
	if cwd, err := os.Getwd(); err == nil {
		if p := filepath.Join(cwd, "config.toml"); fileExists(p) {
			return p
		}
	}

	// 3. Binary-relative. Resolve symlinks first so ~/bin/juked follows the
	// chain all the way to cli/dist/juked, whose parent is cli/.
	if exe, err := os.Executable(); err == nil {
		if real, err := filepath.EvalSymlinks(exe); err == nil {
			exe = real
		}
		exeDir := filepath.Dir(exe)
		// Check the binary's directory (e.g. cli/dist/config.toml).
		if p := filepath.Join(exeDir, "config.toml"); fileExists(p) {
			return p
		}
		// Check the binary's parent directory (e.g. cli/config.toml when
		// the binary lives at cli/dist/juked).
		if p := filepath.Join(filepath.Dir(exeDir), "config.toml"); fileExists(p) {
			return p
		}
	}

	return "" // no file found; Load uses defaults + env overrides
}

func fileExists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

// ResolvePaths returns the filesystem locations for the running platform.
// Config is resolved by FindConfigPath (project-local, then platform fallback).
// Data and Socket remain platform-specific so the session token and IPC socket
// never follow the source tree.
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
		Config: resolveConfig(filepath.Join(base, "config.toml")),
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
		Config: resolveConfig(filepath.Join(base, "config.toml")),
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
		Config: resolveConfig(filepath.Join(cfgDir, "juke", "config.toml")),
		Data:   filepath.Join(dataDir, "juke"),
		Socket: sockPath,
	}, nil
}

// resolveConfig returns FindConfigPath() when it finds a project-local file,
// otherwise falls back to the platform-specific path.
func resolveConfig(platformPath string) string {
	if p := FindConfigPath(); p != "" {
		return p
	}
	return platformPath
}
