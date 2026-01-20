import { API_BASE_URL } from '@shared/api/apiClient';

export const SPOTIFY_AUTH_PATH = new URL('/api/v1/social-auth/login/spotify/', API_BASE_URL).toString();
