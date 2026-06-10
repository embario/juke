package api

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"sync"
	"time"
)

// APIError represents a non-2xx response from the Juke backend.
type APIError struct {
	StatusCode int
	Body       string
}

func (e *APIError) Error() string {
	return fmt.Sprintf("api: HTTP %d: %s", e.StatusCode, e.Body)
}

// NetworkError is returned when the HTTP request fails at the transport level
// (connection refused, reset, timeout, DNS failure, etc.) before any HTTP
// response is received. It gives a human-readable message instead of a raw
// Go net error.
type NetworkError struct {
	URL   string
	Cause error
}

func (e *NetworkError) Error() string {
	switch {
	case isConnRefused(e.Cause):
		return fmt.Sprintf("cannot reach backend at %s (connection refused — is the server running?)", e.URL)
	case isConnReset(e.Cause), isEOF(e.Cause):
		return fmt.Sprintf("backend at %s reset the connection (server may be starting up — try again in a moment)", e.URL)
	case isTimeout(e.Cause):
		return fmt.Sprintf("backend at %s timed out", e.URL)
	default:
		// Unwrap url.Error so the message doesn't repeat the full endpoint path.
		cause := e.Cause
		var urlErr interface{ Unwrap() error }
		if errors.As(cause, &urlErr) {
			if inner := urlErr.Unwrap(); inner != nil {
				cause = inner
			}
		}
		return fmt.Sprintf("cannot reach backend at %s: %s", e.URL, cause)
	}
}

func (e *NetworkError) Unwrap() error { return e.Cause }

func isConnRefused(err error) bool {
	var opErr *net.OpError
	if errors.As(err, &opErr) {
		if opErr.Op == "dial" {
			var sysErr *net.AddrError
			if errors.As(opErr.Err, &sysErr) {
				return true
			}
			return isRefusedSyscall(opErr.Err)
		}
	}
	return false
}

func isConnReset(err error) bool {
	var opErr *net.OpError
	if errors.As(err, &opErr) {
		return isResetSyscall(opErr.Err)
	}
	return false
}

func isTimeout(err error) bool {
	var netErr net.Error
	return errors.As(err, &netErr) && netErr.Timeout()
}

func isEOF(err error) bool {
	return errors.Is(err, io.EOF) || errors.Is(err, io.ErrUnexpectedEOF)
}

// Client is a thin wrapper around net/http that injects the auth token header
// and deserialises responses into caller-supplied structs.
type Client struct {
	baseURL    string
	httpClient *http.Client

	mu    sync.RWMutex
	token string
}

// New returns a Client targeting baseURL (no trailing slash).
func New(baseURL string) *Client {
	return &Client{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 15 * time.Second,
		},
	}
}

// SetToken updates the auth token used for subsequent requests.
func (c *Client) SetToken(token string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.token = token
}

// ClearToken removes the stored auth token.
func (c *Client) ClearToken() {
	c.SetToken("")
}

// Do executes an HTTP request.
//   - method: "GET", "POST", etc.
//   - path: relative path, e.g. "/api/v1/auth/api-auth-token/". Leading slash required.
//   - body: serialised to JSON if non-nil.
//   - dst: unmarshalled from the response body if non-nil and response is 2xx.
//
// Non-2xx responses are returned as *APIError.
func (c *Client) Do(method, path string, body, dst any) error {
	var reqBody io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("api: marshal request body: %w", err)
		}
		reqBody = bytes.NewReader(data)
	}

	req, err := http.NewRequest(method, c.baseURL+path, reqBody)
	if err != nil {
		return fmt.Errorf("api: build request: %w", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	req.Header.Set("Accept", "application/json")

	c.mu.RLock()
	tok := c.token
	c.mu.RUnlock()
	if tok != "" {
		req.Header.Set("Authorization", "Token "+tok)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return &NetworkError{URL: c.baseURL, Cause: err}
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20)) // 1 MiB max
	if err != nil {
		return fmt.Errorf("api: read response: %w", err)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return &APIError{StatusCode: resp.StatusCode, Body: string(respBody)}
	}

	if dst != nil && len(respBody) > 0 {
		if err := json.Unmarshal(respBody, dst); err != nil {
			return fmt.Errorf("api: decode response: %w", err)
		}
	}
	return nil
}
