import { afterEach, describe, expect, it, vi } from 'vitest';

describe('auth constants', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('uses PUBLIC_BACKEND_URL for Spotify auth paths', async () => {
    vi.stubEnv('PUBLIC_BACKEND_URL', 'http://auth.local:8000');
    vi.stubEnv('BACKEND_URL', 'http://localhost:8000');

    const { SPOTIFY_AUTH_PATH } = await import('./constants');

    expect(SPOTIFY_AUTH_PATH).toBe('http://auth.local:8000/api/v1/social-auth/login/spotify/');
  });
});
