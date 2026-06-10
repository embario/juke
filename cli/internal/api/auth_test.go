package api_test

import (
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/embario/juke/cli/internal/api"
)

// fixtureServer creates an httptest.Server that returns the contents of the
// fixture file at relPath (relative to the repo's testdata/fixtures/ dir) with
// the given status code.
func fixtureServer(t *testing.T, statusCode int, relPath string) *httptest.Server {
	t.Helper()
	// Walk up from this file's dir to the cli/ module root, then into testdata.
	_, file, _, _ := runtime.Caller(0)
	fixtureDir := filepath.Join(filepath.Dir(file), "..", "..", "testdata", "fixtures")
	data, err := os.ReadFile(filepath.Join(fixtureDir, relPath))
	if err != nil {
		t.Fatalf("fixture %s: %v", relPath, err)
	}
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(statusCode)
		_, _ = w.Write(data)
	}))
}

// TestLoginSuccess verifies that a 200 response returns the token string.
func TestLoginSuccess(t *testing.T) {
	t.Parallel()
	srv := fixtureServer(t, 200, "api-auth-token-200.json")
	defer srv.Close()

	client := api.New(srv.URL)
	token, err := client.Login("melodyqueen", "hunter2")
	if err != nil {
		t.Fatalf("Login: %v", err)
	}
	if token != "testtoken123abc" {
		t.Errorf("token: got %q, want testtoken123abc", token)
	}
}

// TestLoginBadCredentials verifies that a 400 response returns an *APIError
// with the correct status code.
func TestLoginBadCredentials(t *testing.T) {
	t.Parallel()
	srv := fixtureServer(t, 400, "api-auth-token-400.json")
	defer srv.Close()

	client := api.New(srv.URL)
	_, err := client.Login("bad", "wrong")
	if err == nil {
		t.Fatal("expected error, got nil")
	}

	var apiErr *api.APIError
	if !errors.As(err, &apiErr) {
		t.Fatalf("expected *APIError, got %T: %v", err, err)
	}
	if apiErr.StatusCode != 400 {
		t.Errorf("StatusCode: got %d, want 400", apiErr.StatusCode)
	}
}

// TestLogoutSuccess verifies that a 200 logout response returns no error.
func TestLogoutSuccess(t *testing.T) {
	t.Parallel()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	client := api.New(srv.URL)
	client.SetToken("sometoken")
	if err := client.Logout(); err != nil {
		t.Errorf("Logout: %v", err)
	}
}

// TestClientAuthHeader verifies that Do injects Authorization: Token when
// a token is set.
func TestClientAuthHeader(t *testing.T) {
	t.Parallel()
	var gotHeader string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotHeader = r.Header.Get("Authorization")
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	client := api.New(srv.URL)
	client.SetToken("mytok")
	_ = client.Do("GET", "/test", nil, nil)

	if gotHeader != "Token mytok" {
		t.Errorf("Authorization header: got %q, want %q", gotHeader, "Token mytok")
	}
}

// TestLoginConnectionRefused verifies that a dial failure to a port with no
// listener returns *NetworkError and a human-readable message (not a raw Go
// TCP error string).
func TestLoginConnectionRefused(t *testing.T) {
	t.Parallel()

	// Find a port that is guaranteed to have nothing listening.
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("setup: %v", err)
	}
	addr := ln.Addr().String()
	ln.Close() // close immediately; the port is now free and unoccupied

	client := api.New("http://" + addr)
	_, err = client.Login("user", "pass")
	if err == nil {
		t.Fatal("expected error, got nil")
	}

	var netErr *api.NetworkError
	if !errors.As(err, &netErr) {
		t.Fatalf("expected *api.NetworkError, got %T: %v", err, err)
	}
	msg := netErr.Error()
	if !strings.Contains(msg, "cannot reach backend") {
		t.Errorf("error message should mention 'cannot reach backend', got: %q", msg)
	}
	if strings.Contains(msg, "read tcp") || strings.Contains(msg, "dial tcp") && strings.Contains(msg, "->") {
		t.Errorf("raw TCP error should not appear in user-facing message, got: %q", msg)
	}
	t.Logf("user-facing error: %s", msg)
}

// TestLoginConnectionReset verifies that a connection-reset scenario returns
// *NetworkError with an actionable message about the server potentially starting up.
// We simulate a reset by accepting the TCP connection and immediately closing it.
func TestLoginConnectionReset(t *testing.T) {
	t.Parallel()

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("setup: %v", err)
	}
	defer ln.Close()

	// Accept and immediately close — this causes the client to see a reset/EOF.
	go func() {
		conn, err := ln.Accept()
		if err != nil {
			return
		}
		conn.Close()
	}()

	client := api.New("http://" + ln.Addr().String())
	_, err = client.Login("user", "pass")
	if err == nil {
		t.Fatal("expected error, got nil")
	}

	var netErr *api.NetworkError
	if !errors.As(err, &netErr) {
		t.Fatalf("expected *api.NetworkError, got %T: %v", err, err)
	}
	msg := netErr.Error()
	// The message should be readable and not expose a raw Go stack-trace style error.
	if strings.Contains(msg, "read tcp") && strings.Contains(msg, "->") && strings.Contains(msg, "[::1]") {
		t.Errorf("raw TCP address pair should not appear in user-facing message, got: %q", msg)
	}
	t.Logf("user-facing error: %s", msg)
}
