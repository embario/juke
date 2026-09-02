import apiClient from '@shared/api/apiClient';

export type VibeAuthorizationRequest = {
  client_id: 'juke-vibe-mac' | 'juke-vibe-ios';
  redirect_uri: 'juke-vibe://auth/callback';
  state: string;
  code_challenge: string;
  code_challenge_method: 'S256';
};

const verifierPattern = /^[A-Za-z0-9_-]{43,128}$/;

export const parseVibeAuthorizationRequest = (
  search: string,
): VibeAuthorizationRequest | null => {
  const params = new URLSearchParams(search);
  const clientId = params.get('client');
  const redirectUri = params.get('redirect_uri');
  const state = params.get('state');
  const challenge = params.get('code_challenge');
  const method = params.get('code_challenge_method');

  if (
    !['juke-vibe-mac', 'juke-vibe-ios'].includes(clientId ?? '') ||
    redirectUri !== 'juke-vibe://auth/callback' ||
    !state ||
    state.length > 512 ||
    !challenge ||
    !verifierPattern.test(challenge) ||
    method !== 'S256'
  ) {
    return null;
  }
  return {
    client_id: clientId as VibeAuthorizationRequest['client_id'],
    redirect_uri: redirectUri,
    state,
    code_challenge: challenge,
    code_challenge_method: method,
  };
};

export const authorizeVibeRequest = async (token: string, search: string) => {
  const request = parseVibeAuthorizationRequest(search);
  if (!request) {
    throw new Error('The Juke Vibe sign-in request is invalid or incomplete.');
  }
  return apiClient.post<{ redirect_to: string }>(
    '/api/v1/auth/vibe/authorize',
    request,
    { token },
  );
};
