import { afterEach, describe, expect, it, vi } from 'vitest';

describe('apiClient', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
  });

  it('uses the browser origin as the API base URL', async () => {
    const { API_BASE_URL } = await import('./apiClient');

    expect(API_BASE_URL).toBe(window.location.origin);
  });

  it('builds same-origin requests for API calls', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ token: 'token-123' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const { apiClient } = await import('./apiClient');

    await apiClient.post('/api/v1/auth/api-auth-token/', {
      username: 'ember',
      password: 'password123',
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      `${window.location.origin}/api/v1/auth/api-auth-token/`,
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
      }),
    );
  });
});
