import apiClient from '@shared/api/apiClient';

export type JournalAuthorizationRequest = {
  client_id: 'juke-journal-mac';
  redirect_uri: 'juke-journal://auth/callback';
  state: string;
  code_challenge: string;
  code_challenge_method: 'S256';
};
const verifierPattern = /^[A-Za-z0-9_-]{43,128}$/;

export const parseJournalAuthorizationRequest = (
  search: string,
): JournalAuthorizationRequest | null => {
  const params = new URLSearchParams(search);
  const clientId = params.get('client');
  const redirectUri = params.get('redirect_uri');
  const state = params.get('state');
  const challenge = params.get('code_challenge');
  const method = params.get('code_challenge_method');

  if (
    clientId !== 'juke-journal-mac' ||
    redirectUri !== 'juke-journal://auth/callback' ||
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
    redirect_uri: redirectUri,
    state,
    code_challenge: challenge,
    code_challenge_method: method,
  };
};

export const authorizeJournalRequest = async (token: string, search: string) => {
  const request = parseJournalAuthorizationRequest(search);
  if (!request) {
    throw new Error('The Juke Journal sign-in request is invalid or incomplete.');
  }
  return apiClient.post<{ redirect_to: string }>(
    '/api/v1/auth/journal/authorize',
    request,
    { token },
  );
};
