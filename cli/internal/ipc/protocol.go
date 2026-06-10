// Package ipc implements the length-prefixed JSON protocol used between
// juked (daemon) and juke (TUI).
//
// Frame wire format:
//
//	┌──────────────┬─────────────────────────────┐
//	│ 4-byte BE u32│  N bytes UTF-8 JSON         │
//	│  = N         │                             │
//	└──────────────┴─────────────────────────────┘
//
// All frames share the Message envelope. Requests carry a client-assigned
// integer ID; server-pushed events carry ID == nil.
package ipc

import (
	"encoding/binary"
	"encoding/json"
	"errors"
	"io"
)

// maxFrameSize is the hard upper bound on a single frame (4 MiB).
// Frames larger than this are rejected to prevent memory exhaustion.
const maxFrameSize = 4 * 1024 * 1024

// ErrFrameTooLarge is returned when a frame exceeds maxFrameSize.
var ErrFrameTooLarge = errors.New("ipc: frame exceeds 4 MiB limit")

// Message is the envelope for every IPC frame.
//
//   - ID nil  → server-pushed event (broadcast)
//   - ID set  → request (TUI→daemon) or response (daemon→TUI)
type Message struct {
	ID   *int            `json:"id"`
	Type string          `json:"type"`
	Data json.RawMessage `json:"data,omitempty"`
}

// MsgID is a convenience constructor for a request message with an integer ID.
func MsgID(id int, typ string, data any) (Message, error) {
	raw, err := json.Marshal(data)
	if err != nil {
		return Message{}, err
	}
	return Message{ID: &id, Type: typ, Data: raw}, nil
}

// MsgEvent constructs a server-pushed event (ID is nil).
func MsgEvent(typ string, data any) (Message, error) {
	raw, err := json.Marshal(data)
	if err != nil {
		return Message{}, err
	}
	return Message{Type: typ, Data: raw}, nil
}

// OKResponse returns a success response echoing the request ID.
func OKResponse(req Message, data any) (Message, error) {
	raw, err := json.Marshal(data)
	if err != nil {
		return Message{}, err
	}
	return Message{ID: req.ID, Type: "ok", Data: raw}, nil
}

// ErrorResponse returns an error response echoing the request ID.
func ErrorResponse(req Message, code, message string) Message {
	data, _ := json.Marshal(map[string]string{"code": code, "message": message})
	return Message{ID: req.ID, Type: "error", Data: data}
}

// WriteFrame marshals m to JSON and writes a length-prefixed frame to w.
// The write is not atomic across two calls on the same writer; callers that
// share a writer must serialise externally.
func WriteFrame(w io.Writer, m Message) error {
	payload, err := json.Marshal(m)
	if err != nil {
		return err
	}
	if len(payload) > maxFrameSize {
		return ErrFrameTooLarge
	}
	var hdr [4]byte
	binary.BigEndian.PutUint32(hdr[:], uint32(len(payload)))
	if _, err := w.Write(hdr[:]); err != nil {
		return err
	}
	_, err = w.Write(payload)
	return err
}

// ReadFrame reads one length-prefixed frame from r and decodes it.
// It uses io.ReadFull so a frame split across multiple TCP/socket segments
// is reassembled transparently.
func ReadFrame(r io.Reader) (Message, error) {
	var hdr [4]byte
	if _, err := io.ReadFull(r, hdr[:]); err != nil {
		return Message{}, err
	}
	n := binary.BigEndian.Uint32(hdr[:])
	if n > maxFrameSize {
		return Message{}, ErrFrameTooLarge
	}
	buf := make([]byte, n)
	if _, err := io.ReadFull(r, buf); err != nil {
		return Message{}, err
	}
	var m Message
	if err := json.Unmarshal(buf, &m); err != nil {
		return Message{}, err
	}
	return m, nil
}
