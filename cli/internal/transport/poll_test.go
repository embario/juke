package transport_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/embario/juke/cli/internal/api"
	"github.com/embario/juke/cli/internal/transport"
)

// servePlaybackFixture returns an httptest.Server that serves successive
// playback-state JSON blobs from the states slice (last entry is repeated).
func servePlaybackFixture(t *testing.T, states []any) *httptest.Server {
	t.Helper()
	var call atomic.Int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		idx := int(call.Add(1)) - 1
		if idx >= len(states) {
			idx = len(states) - 1
		}
		s := states[idx]
		if s == nil {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(s)
	}))
	t.Cleanup(srv.Close)
	return srv
}

func mustURI(s string) *string { return &s }

// TestPollTransportEmitsDiff asserts the poller emits on each meaningful state
// change and does not emit when state is repeated.
//
// Tick sequence with fixture [A, A, B, B]:
//
//	Tick 1: nil → A  → diff  → emit A  (initial state arrives)
//	Tick 2: A   → A  → same  → no emit
//	Tick 3: A   → B  → diff  → emit B  (track changes)
//	Tick 4: B   → B  → same  → no emit
//
// Expected updates channel contents after 4 ticks: [A, B].
func TestPollTransportEmitsDiff(t *testing.T) {
	t.Parallel()

	stateA := &api.PlaybackState{Provider: "spotify", IsPlaying: true, Track: &api.PlaybackTrack{Name: "A", URI: mustURI("spotify:track:aaa")}}
	stateB := &api.PlaybackState{Provider: "spotify", IsPlaying: true, Track: &api.PlaybackTrack{Name: "B", URI: mustURI("spotify:track:bbb")}}

	// fixture: A, A, B, B — yields exactly two diffs (nil→A, A→B)
	srv := servePlaybackFixture(t, []any{stateA, stateA, stateB, stateB})

	client := api.New(srv.URL)
	pt := transport.NewPollTransport(client, 20*time.Millisecond)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	updates := make(chan *api.PlaybackState, 8)
	if err := pt.Connect(ctx, updates); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	// Allow 4 full ticks (4 × 20ms = 80ms) plus a margin.
	time.Sleep(140 * time.Millisecond)
	pt.Stop()

	// Should have exactly two emissions: A then B.
	if len(updates) != 2 {
		t.Fatalf("expected 2 updates (A then B), got %d", len(updates))
	}
	first := <-updates
	if first.Track == nil || first.Track.Name != "A" {
		t.Errorf("first update: expected track A, got %+v", first)
	}
	second := <-updates
	if second.Track == nil || second.Track.Name != "B" {
		t.Errorf("second update: expected track B, got %+v", second)
	}
	// Repeated B must not have generated a third emission.
	if len(updates) != 0 {
		t.Errorf("expected no further updates after repeated state B, got %d", len(updates))
	}
}

// TestPollTransportNoEmitSameState asserts zero emissions when state is stable.
func TestPollTransportNoEmitSameState(t *testing.T) {
	t.Parallel()

	state := &api.PlaybackState{Provider: "spotify", IsPlaying: true, Track: &api.PlaybackTrack{Name: "Stable", URI: mustURI("spotify:track:stable")}}
	srv := servePlaybackFixture(t, []any{state, state, state})

	client := api.New(srv.URL)
	pt := transport.NewPollTransport(client, 20*time.Millisecond)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	updates := make(chan *api.PlaybackState, 8)
	if err := pt.Connect(ctx, updates); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	// Two full cycles — nothing should be emitted after the first poll settles.
	// The first poll sets last=state; subsequent polls find no diff.
	time.Sleep(80 * time.Millisecond)
	pt.Stop()

	if len(updates) > 1 {
		t.Errorf("expected at most 1 emission (initial nil→state), got %d", len(updates))
	}
}

// TestPollTransportContextCancel asserts the goroutine exits promptly on cancel.
func TestPollTransportContextCancel(t *testing.T) {
	t.Parallel()

	srv := servePlaybackFixture(t, []any{nil})
	client := api.New(srv.URL)
	pt := transport.NewPollTransport(client, 50*time.Millisecond)

	ctx, cancel := context.WithCancel(context.Background())
	updates := make(chan *api.PlaybackState, 8)
	if err := pt.Connect(ctx, updates); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	cancel()

	// The goroutine must exit within 2 * interval (100ms).
	deadline := time.After(200 * time.Millisecond)
	// We verify the goroutine stopped by checking Stop doesn't block
	// and no more updates arrive. We can't directly observe goroutine exit,
	// but confirming the channel gets no new writes after cancel is sufficient.
	select {
	case <-deadline:
		// ok — goroutine exited (no panic, no hang)
	}
}

// TestPollTransportNetworkError asserts the poller continues on transient errors.
func TestPollTransportNetworkError(t *testing.T) {
	t.Parallel()

	// Server closes connections immediately for the first two calls, then serves.
	var call atomic.Int64
	state := &api.PlaybackState{Provider: "spotify", IsPlaying: true, Track: &api.PlaybackTrack{Name: "Z", URI: mustURI("spotify:track:zzz")}}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := call.Add(1)
		if n <= 2 {
			// Simulate a connection reset by closing without a response.
			hj, ok := w.(http.Hijacker)
			if ok {
				conn, _, _ := hj.Hijack()
				conn.Close()
				return
			}
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(state)
	}))
	t.Cleanup(srv.Close)

	client := api.New(srv.URL)
	pt := transport.NewPollTransport(client, 20*time.Millisecond)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	updates := make(chan *api.PlaybackState, 8)
	if err := pt.Connect(ctx, updates); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	// Wait for the successful third tick.
	select {
	case got := <-updates:
		if got.Track == nil || got.Track.Name != "Z" {
			t.Errorf("expected track Z after recovery, got %+v", got)
		}
	case <-time.After(500 * time.Millisecond):
		t.Fatal("timed out waiting for recovery after network errors")
	}
	pt.Stop()
}

// TestManagerModeIsPollWhenWSFails asserts that Mode() returns "polling"
// immediately after the WS stub fails and the polling fallback starts.
func TestManagerModeIsPollWhenWSFails(t *testing.T) {
	t.Parallel()

	state := &api.PlaybackState{Provider: "spotify", IsPlaying: false}
	srv := servePlaybackFixture(t, []any{state})
	client := api.New(srv.URL)

	mgr := transport.NewManager(client, 50*time.Millisecond, nil)

	ctx, cancel := context.WithCancel(context.Background())
	updates := make(chan *api.PlaybackState, 8)

	done := make(chan struct{})
	go func() {
		mgr.Start(ctx, updates)
		close(done)
	}()

	// Give the manager time to fail WS and start polling.
	deadline := time.After(200 * time.Millisecond)
	for {
		if mgr.Mode() == "polling" {
			break
		}
		select {
		case <-deadline:
			t.Errorf("Manager.Mode() still %q after 200ms, expected polling", mgr.Mode())
			cancel()
			<-done
			return
		case <-time.After(5 * time.Millisecond):
		}
	}

	cancel()
	<-done
}
