import apiClient from '@shared/api/apiClient';
import type { Album, Artist, CatalogResults, Track } from '../types';

type Resource = 'albums' | 'artists' | 'tracks' | 'genres';

const withResults = <T>(response: unknown): T[] => {
  if (!response || typeof response !== 'object') {
    return [];
  }

  const data = response as { results?: T[] };
  return data.results ?? [];
};

const fetchCollection = async <T>(resource: Resource, token: string, query: string) => {
  const queryParams = query
    ? {
        search: query,
        q: query,
        external: 'true',
      }
    : undefined;
  const response = await apiClient.get(`/api/v1/${resource}/`, {
    token,
    query: queryParams,
  });
  return withResults<T>(response);
};

export const fetchAllCatalogResources = async (token: string, query: string): Promise<CatalogResults> => {
  const [albums, artists, tracks] = await Promise.all([
    fetchCollection<Album>('albums', token, query),
    fetchCollection<Artist>('artists', token, query),
    fetchCollection<Track>('tracks', token, query),
  ]);

  return {
    genres: [],
    albums,
    artists,
    tracks,
  };
};
