package ipc_test

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"io"
	"net"
	"strings"
	"sync"
	"testing"

	"github.com/embario/juke/cli/internal/ipc"
)

func id(n int) *int { return &n }

// TestFrameRoundTrip verifies that a message survives a WriteFrame/ReadFrame cycle.
func TestFrameRoundTrip(t *testing.T) {
	t.Parallel()
	want := ipc.Message{
		ID:   id(42),
		Type: "session.state",
		Data: json.RawMessage(`{"authenticated":false}`),
	}

	var buf bytes.Buffer
	if err := ipc.WriteFrame(&buf, want); err != nil {
		t.Fatalf("WriteFrame: %v", err)
	}

	got, err := ipc.ReadFrame(&buf)
	if err != nil {
		t.Fatalf("ReadFrame: %v", err)
	}

	if got.Type != want.Type {
		t.Errorf("Type: got %q, want %q", got.Type, want.Type)
	}
	if got.ID == nil || *got.ID != *want.ID {
		t.Errorf("ID: got %v, want %v", got.ID, want.ID)
	}
	if string(got.Data) != string(want.Data) {
		t.Errorf("Data: got %s, want %s", got.Data, want.Data)
	}
}

// TestFrameNilID verifies that server-pushed events (ID == nil) survive the
// round-trip with ID still nil.
func TestFrameNilID(t *testing.T) {
	t.Parallel()
	want := ipc.Message{Type: "session.changed", Data: json.RawMessage(`{}`)}

	var buf bytes.Buffer
	if err := ipc.WriteFrame(&buf, want); err != nil {
		t.Fatalf("WriteFrame: %v", err)
	}
	got, err := ipc.ReadFrame(&buf)
	if err != nil {
		t.Fatalf("ReadFrame: %v", err)
	}
	if got.ID != nil {
		t.Errorf("ID: got %v, want nil", got.ID)
	}
	if got.Type != "session.changed" {
		t.Errorf("Type: got %q", got.Type)
	}
}

// TestFrameShortRead verifies that ReadFrame reassembles a frame delivered in
// two separate Write calls (header first, payload second).
func TestFrameShortRead(t *testing.T) {
	t.Parallel()

	msg := ipc.Message{ID: id(1), Type: "ping", Data: json.RawMessage(`"pong"`)}

	// Encode manually so we can split the write.
	payload, err := json.Marshal(msg)
	if err != nil {
		t.Fatal(err)
	}
	var hdr [4]byte
	binary.BigEndian.PutUint32(hdr[:], uint32(len(payload)))

	pr, pw := io.Pipe()

	// Writer goroutine: header and payload in two separate writes.
	go func() {
		_, _ = pw.Write(hdr[:])
		_, _ = pw.Write(payload)
		pw.Close()
	}()

	got, err := ipc.ReadFrame(pr)
	if err != nil {
		t.Fatalf("ReadFrame: %v", err)
	}
	if got.Type != "ping" {
		t.Errorf("Type: got %q, want ping", got.Type)
	}
}

// TestFrameConcurrentWrite verifies that 20 goroutines writing distinct frames
// to a net.Conn pipe produce 20 individually valid frames on the other end
// with no JSON corruption.
func TestFrameConcurrentWrite(t *testing.T) {
	t.Parallel()
	const n = 20

	server, client := net.Pipe()
	defer server.Close()
	defer client.Close()

	var wg sync.WaitGroup
	var mu sync.Mutex // serialise writes so frames are not interleaved

	// Write n frames concurrently, each serialised through mu.
	for i := range n {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			m, _ := ipc.MsgID(i, "test", map[string]int{"seq": i})
			mu.Lock()
			_ = ipc.WriteFrame(client, m)
			mu.Unlock()
		}(i)
	}

	// Read n frames from the server side.
	seen := make(map[int]bool)
	for range n {
		msg, err := ipc.ReadFrame(server)
		if err != nil {
			t.Fatalf("ReadFrame: %v", err)
		}
		if msg.Type != "test" {
			t.Errorf("unexpected type %q", msg.Type)
		}
		var body map[string]int
		if err := json.Unmarshal(msg.Data, &body); err != nil {
			t.Fatalf("unmarshal body: %v (raw: %s)", err, msg.Data)
		}
		seen[body["seq"]] = true
	}

	wg.Wait()

	for i := range n {
		if !seen[i] {
			t.Errorf("missing frame seq=%d", i)
		}
	}
}

// TestFrameTooLarge verifies that ReadFrame rejects a frame whose declared
// length exceeds maxFrameSize without allocating the payload.
func TestFrameTooLarge(t *testing.T) {
	t.Parallel()

	var buf bytes.Buffer
	// Write a header claiming 5 MiB payload without any payload bytes.
	var hdr [4]byte
	binary.BigEndian.PutUint32(hdr[:], 5*1024*1024)
	buf.Write(hdr[:])

	_, err := ipc.ReadFrame(&buf)
	if err != ipc.ErrFrameTooLarge {
		t.Errorf("got %v, want ErrFrameTooLarge", err)
	}
}

// TestWriteFrameTooLarge verifies that WriteFrame rejects payloads whose
// marshaled size exceeds 4 MiB and writes no bytes to the writer.
func TestWriteFrameTooLarge(t *testing.T) {
	t.Parallel()

	// A JSON string of >4 MiB of 'x' characters is valid JSON and will produce
	// a marshaled Message payload well above maxFrameSize.
	largeStr := `"` + strings.Repeat("x", 5*1024*1024) + `"`
	msg := ipc.Message{Type: "big", Data: json.RawMessage(largeStr)}

	var buf bytes.Buffer
	err := ipc.WriteFrame(&buf, msg)
	if err != ipc.ErrFrameTooLarge {
		t.Errorf("got %v, want ErrFrameTooLarge", err)
	}
	if buf.Len() != 0 {
		t.Errorf("buffer should be empty after rejected write, got %d bytes", buf.Len())
	}
}
