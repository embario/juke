package ipc_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"sync"
	"testing"
	"time"

	"github.com/embario/juke/cli/internal/ipc"
)

// TestClientRequestConcurrent sends 10 concurrent requests on one client and
// verifies each receives its own response with no id cross-talk.
func TestClientRequestConcurrent(t *testing.T) {
	t.Parallel()
	const n = 10

	// Fake server: echoes each request back as "ok" with the same id and data.
	handler := func(req ipc.Message) *ipc.Message {
		resp, _ := ipc.OKResponse(req, json.RawMessage(req.Data))
		return &resp
	}
	srv, addr := startTestServer(t, handler)
	_ = srv

	conn, err := net.Dial("unix", addr)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	client := ipc.NewClient(conn)
	defer client.Close()

	type result struct {
		seq int
		err error
	}
	results := make(chan result, n)

	var wg sync.WaitGroup
	for i := range n {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			resp, err := client.Request("test", map[string]int{"seq": i})
			if err != nil {
				results <- result{i, err}
				return
			}
			var body map[string]int
			if err := json.Unmarshal(resp.Data, &body); err != nil {
				results <- result{i, fmt.Errorf("unmarshal: %w", err)}
				return
			}
			if body["seq"] != i {
				results <- result{i, fmt.Errorf("seq mismatch: got %d, want %d", body["seq"], i)}
				return
			}
			results <- result{i, nil}
		}(i)
	}

	wg.Wait()
	close(results)

	for r := range results {
		if r.err != nil {
			t.Errorf("goroutine %d: %v", r.seq, r.err)
		}
	}
}

// TestClientEventChannel verifies that server-pushed events (id: null) are
// delivered to the Events() channel.
func TestClientEventChannel(t *testing.T) {
	t.Parallel()

	// Handler that sends an event after accepting the first request.
	var srvRef *ipc.Server
	var once sync.Once
	handler := func(req ipc.Message) *ipc.Message {
		once.Do(func() {
			// Push an event after a tiny delay so the response goes first.
			go func() {
				time.Sleep(10 * time.Millisecond)
				ev, _ := ipc.MsgEvent("session.changed", map[string]bool{"authenticated": true})
				srvRef.Broadcast(ev)
			}()
		})
		resp, _ := ipc.OKResponse(req, json.RawMessage(`{}`))
		return &resp
	}

	srv, addr := startTestServer(t, handler)
	srvRef = srv

	conn, err := net.Dial("unix", addr)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	client := ipc.NewClient(conn)
	defer client.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	// Trigger the server-side event emission.
	_, _ = client.Request("ping", map[string]string{})

	select {
	case ev := <-client.Events():
		if ev.Type != "session.changed" {
			t.Errorf("event type: got %q, want session.changed", ev.Type)
		}
	case <-ctx.Done():
		t.Fatal("timed out waiting for server-pushed event")
	}
}
