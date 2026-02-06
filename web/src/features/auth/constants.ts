import { API_BASE_URL } from '@shared/api/apiClient';

export const SPOTIFY_AUTH_PATH = new URL('/api/v1/social-auth/login/spotify/', API_BASE_URL).toString();
export const SPOTIFY_CONNECT_PATH = new URL('/api/v1/auth/connect/spotify/', API_BASE_URL).toString();

export const buildSpotifyConnectPath = (token?: string | null, returnTo?: string) => {
  const target = new URL(SPOTIFY_CONNECT_PATH);
  if (token) {
    target.searchParams.set('token', token);
  }
  if (returnTo) {
    target.searchParams.set('return_to', returnTo);
  }
  return target.toString();
};
