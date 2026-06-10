package ipc_test

import (
	"context"
	"encoding/json"
	"net"
	"sync"
	"testing"
	"time"

	"github.com/embario/juke/cli/internal/ipc"
)

// echoHandler returns the request unchanged (type "ok", same id, same data).
func echoHandler(req ipc.Message) *ipc.Message {
	resp, _ := ipc.OKResponse(req, json.RawMessage(req.Data))
	return &resp
}

// TestServerBroadcast verifies that a broadcast reaches two simultaneously
// connected clients within a reasonable deadline.
func TestServerBroadcast(t *testing.T) {
	t.Parallel()

	srv, addr := startTestServer(t, echoHandler)
	const clients = 2

	received := make(chan ipc.Message, clients)

	var wg sync.WaitGroup
	for range clients {
		wg.Add(1)
		go func() {
			defer wg.Done()
			conn, err := net.Dial("unix", addr)
			if err != nil {
				t.Errorf("dial: %v", err)
				return
			}
			defer conn.Close()
			// Signal ready by reading one frame (the broadcast).
			msg, err := ipc.ReadFrame(conn)
			if err != nil {
				t.Errorf("ReadFrame: %v", err)
				return
			}
			received <- msg
		}()
	}

	// Give clients time to connect.
	time.Sleep(50 * time.Millisecond)

	ev, _ := ipc.MsgEvent("test.broadcast", map[string]string{"hello": "world"})
	srv.Broadcast(ev)

	// Wait for both reads or timeout.
	done := make(chan struct{})
	go func() { wg.Wait(); close(done) }()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for broadcast delivery")
	}

	if len(received) != clients {
		t.Errorf("got %d deliveries, want %d", len(received), clients)
	}
}

// TestServerConcurrentClients verifies that 10 concurrent clients can each
// send a session.state request and receive a response without panics or races.
func TestServerConcurrentClients(t *testing.T) {
	t.Parallel()

	_, addr := startTestServer(t, echoHandler)

	var wg sync.WaitGroup
	const clients = 10

	for i := range clients {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			conn, err := net.Dial("unix", addr)
			if err != nil {
				t.Errorf("client %d dial: %v", i, err)
				return
			}
			defer conn.Close()

			req, _ := ipc.MsgID(i, "session.state", map[string]string{})
			if err := ipc.WriteFrame(conn, req); err != nil {
				t.Errorf("client %d WriteFrame: %v", i, err)
				return
			}
			resp, err := ipc.ReadFrame(conn)
			if err != nil {
				t.Errorf("client %d ReadFrame: %v", i, err)
				return
			}
			if resp.Type != "ok" {
				t.Errorf("client %d: expected type ok, got %q", i, resp.Type)
			}
			if resp.ID == nil || *resp.ID != i {
				t.Errorf("client %d: response ID mismatch: got %v", i, resp.ID)
			}
		}(i)
	}

	wg.Wait()
}

// startTestServer creates an in-process unix socket server for testing.
// It registers t.Cleanup to shut down the server.
// Returns the *Server (for Broadcast) and the socket path string.
func startTestServer(t *testing.T, h ipc.Handler) (*ipc.Server, string) {
	t.Helper()
	socketPath := t.TempDir() + "/test.sock"
	ln, err := net.Listen("unix", socketPath)
	if err != nil {
		t.Fatalf("listen: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	srv := ipc.NewServer(ln, h)

	go func() { _ = srv.Accept(ctx) }()

	t.Cleanup(func() {
		cancel()
		srv.Close()
	})

	return srv, socketPath
}
