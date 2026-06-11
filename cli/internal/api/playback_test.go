package api_test

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"github.com/embario/juke/cli/internal/api"
)

func fixtureBytes(t *testing.T, name string) []byte {
	t.Helper()
	// testdata lives two levels up from internal/api/
	data, err := os.ReadFile("../../testdata/fixtures/" + name)
	if err != nil {
		t.Fatalf("read fixture %s: %v", name, err)
	}
	return data
}

// TestPlaybackStateSuccess verifies that a 200 with the playing fixture
// returns a populated *PlaybackState with IsPlaying == true.
func TestPlaybackStateSuccess(t *testing.T) {
	t.Parallel()
	body := fixtureBytes(t, "playback-state-playing.json")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/playback/state/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer srv.Close()

	client := api.New(srv.URL)
	client.SetToken("testtoken")

	ps, err := client.PlaybackState()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if ps == nil {
		t.Fatal("expected non-nil PlaybackState")
	}
	if !ps.IsPlaying {
		t.Error("IsPlaying should be true")
	}
	if ps.Track == nil {
		t.Fatal("Track should be set")
	}
	if ps.Track.Name != "So What" {
		t.Errorf("Track.Name: got %q, want %q", ps.Track.Name, "So What")
	}
	if len(ps.Track.Artists) == 0 || ps.Track.Artists[0].Name != "Miles Davis" {
		t.Errorf("expected artist Miles Davis, got %+v", ps.Track.Artists)
	}
}

// TestPlaybackStateStopped verifies the stopped fixture: IsPlaying false, track present.
func TestPlaybackStateStopped(t *testing.T) {
	t.Parallel()
	body := fixtureBytes(t, "playback-state-stopped.json")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	defer srv.Close()

	client := api.New(srv.URL)
	ps, err := client.PlaybackState()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if ps == nil {
		t.Fatal("expected non-nil PlaybackState for stopped state")
	}
	if ps.IsPlaying {
		t.Error("IsPlaying should be false for stopped state")
	}
	if ps.Track == nil {
		t.Fatal("Track should be present in stopped state")
	}
}

// TestPlaybackStateNotPlaying verifies that HTTP 204 returns (nil, nil).
func TestPlaybackStateNotPlaying(t *testing.T) {
	t.Parallel()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()

	client := api.New(srv.URL)
	ps, err := client.PlaybackState()
	if err != nil {
		t.Fatalf("expected nil error for 204, got: %v", err)
	}
	if ps != nil {
		t.Errorf("expected nil PlaybackState for 204, got: %+v", ps)
	}
}

// TestPlaybackStateNetworkError verifies that a server that drops the connection
// returns *api.NetworkError with a human-readable message — no raw Go net/http
// error strings exposed to the caller.
func TestPlaybackStateNetworkError(t *testing.T) {
	t.Parallel()

	// Hijack the connection and close it without writing any HTTP response,
	// simulating a mid-flight connection reset.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hj, ok := w.(http.Hijacker)
		if !ok {
			http.Error(w, "hijack not supported", http.StatusInternalServerError)
			return
		}
		conn, _, _ := hj.Hijack()
		conn.Close()
	}))
	defer srv.Close()

	client := api.New(srv.URL)
	_, err := client.PlaybackState()
	if err == nil {
		t.Fatal("expected a non-nil error for a closed connection")
	}

	// Must surface as *api.NetworkError, not a raw net/http or url.Error.
	var netErr *api.NetworkError
	if !errors.As(err, &netErr) {
		t.Fatalf("expected *api.NetworkError, got %T: %v", err, err)
	}

	// The message must be human-readable: none of the raw Go transport strings
	// that would be meaningless to an end user should appear.
	msg := netErr.Error()
	rawPhrases := []string{
		"dial tcp",
		"read tcp",
		"connection reset by peer",
		"syscall.ECONNRESET",
		"&url.Error",
	}
	for _, phrase := range rawPhrases {
		if strings.Contains(msg, phrase) {
			t.Errorf("error message leaks raw transport string %q\nfull message: %q", phrase, msg)
		}
	}

	// Must still point the user at the backend so they know where to look.
	if !strings.Contains(msg, "backend") {
		t.Errorf("error message should reference the backend, got: %q", msg)
	}
}
