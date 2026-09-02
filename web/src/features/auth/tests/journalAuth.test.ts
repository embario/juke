import { describe, expect, it, vi } from 'vitest';
import apiClient from '@shared/api/apiClient';
import { authorizeJournalRequest, parseJournalAuthorizationRequest } from '../api/journalAuth';

vi.mock('@shared/api/apiClient', () => ({
  default: { post: vi.fn() },
}));

const validSearch = `?client=juke-journal-mac&redirect_uri=${encodeURIComponent(
  'juke-journal://auth/callback',
)}&state=state-123&code_challenge=${'a'.repeat(43)}&code_challenge_method=S256`;

describe('Journal browser authentication bridge', () => {
  it('parses only the allowlisted Mac client contract', () => {
    expect(parseJournalAuthorizationRequest(validSearch)).toEqual({
      client_id: 'juke-journal-mac',
      redirect_uri: 'juke-journal://auth/callback',
      state: 'state-123',
      code_challenge: 'a'.repeat(43),
      code_challenge_method: 'S256',
    });
    expect(parseJournalAuthorizationRequest(validSearch.replace('juke-journal-mac', 'evil'))).toBeNull();
    expect(parseJournalAuthorizationRequest(validSearch.replace('S256', 'plain'))).toBeNull();
  });

  it('sends the validated request with the signed-in Juke token', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ redirect_to: 'juke-journal://auth/callback?code=one' });
    await authorizeJournalRequest('token-123', validSearch);
    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/v1/auth/journal/authorize',
      expect.objectContaining({ client_id: 'juke-journal-mac' }),
      { token: 'token-123' },
    );
  });
});
