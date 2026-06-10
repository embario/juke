package ipc

import (
	"fmt"
	"io"
	"net"
	"sync"
	"sync/atomic"
)

// Client is the TUI-side IPC connection to juked.
//
// Requests are correlated by ID: the caller assigns an ID, the server echoes
// it in the response, and the client delivers the response to the waiting
// goroutine. Server-pushed events (ID == nil) are delivered to Events().
type Client struct {
	conn   net.Conn
	nextID atomic.Int64

	mu      sync.Mutex
	pending map[int]chan Message

	events chan Message
	done   chan struct{}
}

// NewClient wraps an existing connection. Callers typically use Dial, not this.
func NewClient(conn net.Conn) *Client {
	c := &Client{
		conn:    conn,
		pending: make(map[int]chan Message),
		events:  make(chan Message, 64),
		done:    make(chan struct{}),
	}
	go c.readLoop()
	return c
}

// DialClient connects to the IPC socket at path and returns a ready Client.
func DialClient(path string) (*Client, error) {
	conn, err := Dial(path)
	if err != nil {
		return nil, err
	}
	return NewClient(conn), nil
}

// Request sends a request of the given type with data serialised as JSON and
// waits for the matching response. Safe to call concurrently.
func (c *Client) Request(typ string, data any) (Message, error) {
	id := int(c.nextID.Add(1))
	msg, err := MsgID(id, typ, data)
	if err != nil {
		return Message{}, fmt.Errorf("ipc client: build request: %w", err)
	}

	ch := make(chan Message, 1)
	c.mu.Lock()
	c.pending[id] = ch
	c.mu.Unlock()

	defer func() {
		c.mu.Lock()
		delete(c.pending, id)
		c.mu.Unlock()
	}()

	if err := WriteFrame(c.conn, msg); err != nil {
		return Message{}, fmt.Errorf("ipc client: write: %w", err)
	}

	select {
	case resp := <-ch:
		return resp, nil
	case <-c.done:
		return Message{}, fmt.Errorf("ipc client: connection closed")
	}
}

// Events returns a channel of server-pushed events (ID == nil).
// The channel is closed when the connection is closed.
func (c *Client) Events() <-chan Message {
	return c.events
}

// Close shuts down the client connection.
func (c *Client) Close() error {
	err := c.conn.Close()
	return err
}

func (c *Client) readLoop() {
	defer close(c.done)
	defer close(c.events)
	for {
		msg, err := ReadFrame(c.conn)
		if err != nil {
			if err != io.EOF {
				_ = err // closed connection — normal
			}
			return
		}
		if msg.ID == nil {
			// Server-pushed event.
			select {
			case c.events <- msg:
			default:
				// Drop if consumer is not keeping up.
			}
			continue
		}
		// Route response to waiting Request call.
		c.mu.Lock()
		ch, ok := c.pending[*msg.ID]
		c.mu.Unlock()
		if ok {
			select {
			case ch <- msg:
			default:
			}
		}
	}
}
