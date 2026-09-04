import apiClient from '@shared/api/apiClient';

type SpotifyConnectTicketResponse = {
  connect_url: string;
  expires_at: string;
};

export async function requestSpotifyConnectUrl(
  token: string | null | undefined,
  returnTo?: string,
): Promise<string> {
  if (!token) {
    throw new Error('Sign in to Juke before connecting Spotify.');
  }
  const response = await apiClient.post<SpotifyConnectTicketResponse>(
    '/api/v1/auth/spotify/connect-ticket/',
    { return_to: returnTo },
    { token },
  );
  return response.connect_url;
}
