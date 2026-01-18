import apiClient from '@shared/api/apiClient';
import type { MusicProfile, MusicProfileSearchResult, MusicProfileUpdatePayload } from '../types';

export const fetchMyProfile = async (token: string): Promise<MusicProfile> => {
  return apiClient.get<MusicProfile>('/api/v1/music-profiles/me/', { token });
};

export const fetchProfileByUsername = async (token: string, username: string): Promise<MusicProfile> => {
  return apiClient.get<MusicProfile>(`/api/v1/music-profiles/${username}/`, { token });
};

export const updateMyProfile = async (
  token: string,
  payload: MusicProfileUpdatePayload,
): Promise<MusicProfile> => {
  return apiClient.patch<MusicProfile>('/api/v1/music-profiles/me/', payload, { token });
};

export const searchProfiles = async (
  token: string,
  query: string,
): Promise<MusicProfileSearchResult[]> => {
  if (!query.trim()) {
    return [];
  }
  const response = await apiClient.get<{ results: MusicProfileSearchResult[] }>(
    '/api/v1/music-profiles/search/',
    {
      token,
      query: { q: query },
    },
  );
  return response.results ?? [];
};
