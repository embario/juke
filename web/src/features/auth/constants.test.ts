import { afterEach, describe, expect, it, vi } from 'vitest';

describe('auth constants', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('uses PUBLIC_BACKEND_URL for Spotify auth paths', async () => {
    vi.stubEnv('PUBLIC_BACKEND_URL', 'http://auth.local:8000');
    vi.stubEnv('BACKEND_URL', 'http://localhost:8000');

    const { SPOTIFY_AUTH_PATH, buildSpotifyConnectPath } = await import('./constants');

    expect(SPOTIFY_AUTH_PATH).toBe('http://auth.local:8000/api/v1/social-auth/login/spotify/');
    expect(buildSpotifyConnectPath('token-123', 'http://neptune:5173/world')).toBe(
      'http://auth.local:8000/api/v1/auth/connect/spotify/?token=token-123&return_to=http%3A%2F%2Fneptune%3A5173%2Fworld',
    );
  });
});
