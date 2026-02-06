import apiClient from '@shared/api/apiClient';
import type { Album, AlbumDetail, Artist, ArtistDetail, CatalogResults, Genre, GenreDetail, Track } from '../types';

type Resource = 'albums' | 'artists' | 'tracks' | 'genres';

const withResults = <T>(response: unknown): T[] => {
  if (!response || typeof response !== 'object') {
    return [];
  }

  const data = response as { results?: T[] };
  return data.results ?? [];
};

const toLower = (value: string) => value.trim().toLowerCase();

const fetchCollection = async <T>(resource: Resource, token: string, query: string) => {
  const trimmedQuery = query.trim();
  const shouldUseExternal = resource !== 'genres' && Boolean(trimmedQuery);
  const queryParams = shouldUseExternal
    ? {
        search: trimmedQuery,
        q: trimmedQuery,
        external: 'true',
      }
    : undefined;

  const response = await apiClient.get(`/api/v1/${resource}/`, {
    token,
    query: queryParams,
  });
  const results = withResults<T>(response);

  if (resource !== 'genres' || !trimmedQuery) {
    return results;
  }

  const target = toLower(trimmedQuery);
  return (results as Genre[]).filter((genre) => toLower(genre.name).includes(target)) as T[];
};

export const fetchAllCatalogResources = async (token: string, query: string): Promise<CatalogResults> => {
  const settled = await Promise.allSettled([
    fetchCollection<Genre>('genres', token, query),
    fetchCollection<Album>('albums', token, query),
    fetchCollection<Artist>('artists', token, query),
    fetchCollection<Track>('tracks', token, query),
  ]);

  const [genresResult, albumsResult, artistsResult, tracksResult] = settled;
  const fulfilledCount = settled.filter((result) => result.status === 'fulfilled').length;
  if (fulfilledCount === 0) {
    throw new Error('Unable to fetch catalog resources.');
  }

  return {
    genres: genresResult.status === 'fulfilled' ? genresResult.value : [],
    albums: albumsResult.status === 'fulfilled' ? albumsResult.value : [],
    artists: artistsResult.status === 'fulfilled' ? artistsResult.value : [],
    tracks: tracksResult.status === 'fulfilled' ? tracksResult.value : [],
  };
};

const fetchDetail = async <T>(token: string, resource: 'genres' | 'artists' | 'albums', id: number): Promise<T> => {
  return apiClient.get<T>(`/api/v1/${resource}/${id}/`, { token });
};

export const fetchGenreDetail = (token: string, id: number): Promise<GenreDetail> => {
  return fetchDetail<GenreDetail>(token, 'genres', id);
};

export const fetchArtistDetail = (token: string, id: number): Promise<ArtistDetail> => {
  return fetchDetail<ArtistDetail>(token, 'artists', id);
};

export const fetchArtistDetailBySpotifyId = async (token: string, spotifyId: string): Promise<ArtistDetail> => {
  return apiClient.get<ArtistDetail>(`/api/v1/artists/${encodeURIComponent(spotifyId)}/`, {
    token,
    query: { external: 'true' },
  });
};

export const fetchAlbumDetailBySpotifyId = async (token: string, spotifyId: string): Promise<AlbumDetail> => {
  return apiClient.get<AlbumDetail>(`/api/v1/albums/${encodeURIComponent(spotifyId)}/`, {
    token,
    query: { external: 'true' },
  });
};

export const fetchAlbumDetail = (token: string, id: number): Promise<AlbumDetail> => {
  return fetchDetail<AlbumDetail>(token, 'albums', id);
};
