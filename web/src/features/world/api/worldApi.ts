import apiClient from '../../../shared/api/apiClient';
import { GlobePoint } from '../types';
import { MusicProfile } from '../../profiles/types';

export type GlobeQueryParams = {
  min_lat: number;
  max_lat: number;
  min_lng: number;
  max_lng: number;
  zoom: number;
  limit?: number;
};

export async function fetchGlobePoints(
  params: GlobeQueryParams,
  token: string | null,
): Promise<GlobePoint[]> {
  return apiClient.get<GlobePoint[]>('/api/v1/music-profiles/globe/', {
    token,
    query: {
      min_lat: params.min_lat,
      max_lat: params.max_lat,
      min_lng: params.min_lng,
      max_lng: params.max_lng,
      zoom: params.zoom,
      limit: params.limit ?? 5000,
    },
  });
}

export async function fetchUserProfile(
  username: string,
  token: string | null,
): Promise<MusicProfile> {
  return apiClient.get<MusicProfile>(`/api/v1/music-profiles/${username}/`, {
    token,
  });
}
