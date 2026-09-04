import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '@shared/api/apiClient';
import { requestSpotifyConnectUrl } from '../api/spotifyConnect';

vi.mock('@shared/api/apiClient', () => ({
  default: { post: vi.fn() },
}));

describe('requestSpotifyConnectUrl', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('exchanges the API token in an authenticated POST instead of putting it in a URL', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      connect_url: 'https://auth.local/connect?ticket=one-time',
      expires_at: '2026-09-04T12:00:00Z',
    });

    const result = await requestSpotifyConnectUrl('secret-token', 'https://juke.local/world');

    expect(result).toBe('https://auth.local/connect?ticket=one-time');
    expect(result).not.toContain('secret-token');
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/auth/spotify/connect-ticket/',
      { return_to: 'https://juke.local/world' },
      { token: 'secret-token' },
    );
  });
});
