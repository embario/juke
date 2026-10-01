import apiClient from '@shared/api/apiClient';

// Mirrors backend settings.VIBE_OAUTH_CLIENTS: each Apple client and the one redirect it may use.
const vibeClientRedirects = {
  'juke-vibe-mac': 'juke-vibe://auth/callback',
  'juke-vibe-ios': 'juke-vibe://auth/callback',
  'juke-app-ios': 'juke-app://auth/callback',
} as const;

type VibeClientId = keyof typeof vibeClientRedirects;

const isVibeClientId = (value: string | null): value is VibeClientId =>
  value !== null && Object.prototype.hasOwnProperty.call(vibeClientRedirects, value);

export type VibeAuthorizationRequest = {
  client_id: VibeClientId;
  redirect_uri: (typeof vibeClientRedirects)[VibeClientId];
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
    !isVibeClientId(clientId) ||
    redirectUri !== vibeClientRedirects[clientId] ||
    !state ||
    state.length > 512 ||
    !challenge ||
    !verifierPattern.test(challenge) ||
    method !== 'S256'
  ) {
    return null;
  }
  return {
    client_id: clientId,
    redirect_uri: vibeClientRedirects[clientId],
    state,
    code_challenge: challenge,
    code_challenge_method: method,
  };
};

export const authorizeVibeRequest = async (token: string, search: string) => {
  const request = parseVibeAuthorizationRequest(search);
  if (!request) {
    throw new Error('The Juke sign-in request is invalid or incomplete.');
  }
  return apiClient.post<{ redirect_to: string }>(
    '/api/v1/auth/vibe/authorize',
    request,
    { token },
  );
};
