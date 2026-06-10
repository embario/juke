package api

import "fmt"

// Login authenticates with the backend and returns the DRF auth token.
// On success the token is stored on the client for subsequent requests.
// Returns *APIError for non-2xx backend responses.
func (c *Client) Login(username, password string) (string, error) {
	payload := map[string]string{
		"username": username,
		"password": password,
	}
	var result struct {
		Token string `json:"token"`
	}
	if err := c.Do("POST", "/api/v1/auth/api-auth-token/", payload, &result); err != nil {
		return "", fmt.Errorf("login: %w", err)
	}
	if result.Token == "" {
		return "", fmt.Errorf("login: backend returned empty token")
	}
	c.SetToken(result.Token)
	return result.Token, nil
}

// Logout invalidates the session on the backend. Best-effort: callers should
// clear local state regardless of whether this call succeeds.
func (c *Client) Logout() error {
	return c.Do("POST", "/api/v1/auth/session/logout/", nil, nil)
}
