import { describe, expect, it, vi } from 'vitest';
import apiClient from '@shared/api/apiClient';
import { authorizeVibeRequest, parseVibeAuthorizationRequest } from '../api/vibeAuth';

vi.mock('@shared/api/apiClient', () => ({
  default: { post: vi.fn() },
}));

const validSearch = `?client=juke-vibe-mac&redirect_uri=${encodeURIComponent(
  'juke-vibe://auth/callback',
)}&state=state-123&code_challenge=${'a'.repeat(43)}&code_challenge_method=S256`;

describe('Vibe browser authentication bridge', () => {
  it('parses only the allowlisted Apple client contracts', () => {
    expect(parseVibeAuthorizationRequest(validSearch)).toEqual({
      client_id: 'juke-vibe-mac',
      redirect_uri: 'juke-vibe://auth/callback',
      state: 'state-123',
      code_challenge: 'a'.repeat(43),
      code_challenge_method: 'S256',
    });
    expect(parseVibeAuthorizationRequest(validSearch.replace('juke-vibe-mac', 'juke-vibe-ios')))
      .toEqual(expect.objectContaining({ client_id: 'juke-vibe-ios' }));
    expect(parseVibeAuthorizationRequest(validSearch.replace('juke-vibe-mac', 'evil'))).toBeNull();
    expect(parseVibeAuthorizationRequest(validSearch.replace('S256', 'plain'))).toBeNull();
  });

  it('pairs the Juke Mac client with its own juke-app redirect', () => {
    const jukeAppSearch = validSearch
      .replace('juke-vibe-mac', 'juke-app-mac')
      .replace(encodeURIComponent('juke-vibe://auth/callback'), encodeURIComponent('juke-app://auth/callback'));
    expect(parseVibeAuthorizationRequest(jukeAppSearch)).toEqual(
      expect.objectContaining({ client_id: 'juke-app-mac', redirect_uri: 'juke-app://auth/callback' }),
    );
    // A client may not borrow another client's redirect scheme.
    expect(parseVibeAuthorizationRequest(validSearch.replace('juke-vibe-mac', 'juke-app-mac'))).toBeNull();
    expect(parseVibeAuthorizationRequest(jukeAppSearch.replace('juke-app-mac', 'juke-vibe-mac'))).toBeNull();
    expect(parseVibeAuthorizationRequest(jukeAppSearch.replace('juke-app-mac', 'toString'))).toBeNull();
  });

  it('sends the validated request with the signed-in Juke token', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ redirect_to: 'juke-vibe://auth/callback?code=one' });
    await authorizeVibeRequest('token-123', validSearch);
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/auth/vibe/authorize',
      expect.objectContaining({ client_id: 'juke-vibe-mac' }),
      { token: 'token-123' },
    );
  });
});
