package api

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// PlaybackState fetches the current playback state from the backend.
//
// Returns (nil, nil) when the backend signals no active session:
//   - HTTP 204 No Content — Spotify not connected or no active device.
//   - HTTP 200 with an empty body — treated the same as 204.
//
// Returns (*NetworkError, …) when the request fails at the transport level
// (connection refused, reset, timeout) before any HTTP response is received.
//
// Returns (*APIError, …) for any other non-2xx response.
func (c *Client) PlaybackState() (*PlaybackState, error) {
	req, err := http.NewRequest("GET", c.baseURL+"/api/v1/playback/state/", nil)
	if err != nil {
		return nil, fmt.Errorf("api: build request: %w", err)
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
		return nil, &NetworkError{URL: c.baseURL, Cause: err}
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return nil, fmt.Errorf("api: read response: %w", err)
	}

	// 204 or empty body → no active session; not an error.
	if resp.StatusCode == http.StatusNoContent || len(body) == 0 {
		return nil, nil
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, &APIError{StatusCode: resp.StatusCode, Body: string(body)}
	}

	var state PlaybackState
	if err := json.Unmarshal(body, &state); err != nil {
		return nil, fmt.Errorf("api: decode response: %w", err)
	}
	return &state, nil
}
