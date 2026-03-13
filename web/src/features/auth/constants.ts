const nodeEnv = typeof process !== 'undefined' ? process.env : undefined;
const SPOTIFY_BASE_URL =
  import.meta.env.PUBLIC_BACKEND_URL ??
  nodeEnv?.PUBLIC_BACKEND_URL ??
  import.meta.env.BACKEND_URL ??
  nodeEnv?.BACKEND_URL ??
  import.meta.env.VITE_API_BASE_URL ??
  nodeEnv?.VITE_API_BASE_URL;

if (!SPOTIFY_BASE_URL) {
  throw new Error('PUBLIC_BACKEND_URL or BACKEND_URL must be defined for Spotify auth.');
}

export const SPOTIFY_AUTH_PATH = new URL('/api/v1/social-auth/login/spotify/', SPOTIFY_BASE_URL).toString();
export const SPOTIFY_CONNECT_PATH = new URL('/api/v1/auth/connect/spotify/', SPOTIFY_BASE_URL).toString();

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
