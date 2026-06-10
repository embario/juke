package ipc

import (
	"context"
	"fmt"
	"io"
	"net"
	"sync"
)

// Handler processes an incoming request and returns a response message.
// A nil return means "send no response" (reserved for future fire-and-forget
// message types; all current handlers always reply).
type Handler func(req Message) *Message

// Server accepts IPC connections and dispatches frames to a registered Handler.
// Each connection gets its own read goroutine and a buffered write channel so a
// slow TUI client cannot block broadcasts to other clients.
type Server struct {
	ln      net.Listener
	handler Handler

	mu    sync.RWMutex
	conns map[*serverConn]struct{}
}

// NewServer creates a Server backed by ln. Every received frame is dispatched
// to h; the returned *Message (if non-nil) is written back to the sender.
func NewServer(ln net.Listener, h Handler) *Server {
	return &Server{
		ln:      ln,
		handler: h,
		conns:   make(map[*serverConn]struct{}),
	}
}

// Accept runs the accept loop until the listener is closed or ctx is cancelled.
// It returns the listener's close error on shutdown, which callers may ignore.
func (s *Server) Accept(ctx context.Context) error {
	go func() {
		<-ctx.Done()
		s.ln.Close()
	}()
	for {
		conn, err := s.ln.Accept()
		if err != nil {
			return err
		}
		sc := &serverConn{
			conn: conn,
			send: make(chan Message, 64),
			done: make(chan struct{}),
		}
		s.add(sc)
		go sc.writeLoop()
		go s.readLoop(sc)
	}
}

// Broadcast sends m to all currently connected clients. Clients whose send
// channel is full are skipped (they will receive the next event instead).
func (s *Server) Broadcast(m Message) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for sc := range s.conns {
		select {
		case sc.send <- m:
		default:
			// client is too slow; skip this event for them
		}
	}
}

// Close stops the server and terminates all live connections.
func (s *Server) Close() error {
	err := s.ln.Close()
	s.mu.Lock()
	defer s.mu.Unlock()
	for sc := range s.conns {
		sc.conn.Close()
		delete(s.conns, sc)
	}
	return err
}

func (s *Server) add(sc *serverConn) {
	s.mu.Lock()
	s.conns[sc] = struct{}{}
	s.mu.Unlock()
}

func (s *Server) remove(sc *serverConn) {
	s.mu.Lock()
	delete(s.conns, sc)
	s.mu.Unlock()
}

func (s *Server) readLoop(sc *serverConn) {
	defer func() {
		s.remove(sc)
		close(sc.done)
		sc.conn.Close()
	}()
	for {
		msg, err := ReadFrame(sc.conn)
		if err != nil {
			if err != io.EOF {
				_ = err // connection closed or reset — normal shutdown
			}
			return
		}
		resp := s.handler(msg)
		if resp != nil {
			select {
			case sc.send <- *resp:
			default:
				fmt.Printf("ipc: send buffer full for conn %v; response dropped\n", sc.conn.RemoteAddr())
			}
		}
	}
}

// serverConn holds per-connection state.
type serverConn struct {
	conn net.Conn
	send chan Message
	done chan struct{}
}

func (sc *serverConn) writeLoop() {
	for msg := range sc.send {
		if err := WriteFrame(sc.conn, msg); err != nil {
			sc.conn.Close()
			return
		}
	}
}
