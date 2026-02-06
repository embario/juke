import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';
import { fetchAlbumDetailBySpotifyId, fetchAllCatalogResources } from './catalogApi';
import apiClient from '@shared/api/apiClient';

vi.mock('@shared/api/apiClient', () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
  },
}));

const mockedGet = apiClient.get as unknown as Mock;

beforeEach(() => {
  mockedGet.mockReset();
  mockedGet.mockResolvedValue({ results: [] });
});

describe('fetchAllCatalogResources', () => {
  const token = 'token-123';

  it('passes external catalog parameters when a query is provided', async () => {
    await fetchAllCatalogResources(token, 'Tool');

    expect(mockedGet).toHaveBeenCalledTimes(4);
    expect(mockedGet).toHaveBeenNthCalledWith(
      1,
      '/api/v1/genres/',
      expect.objectContaining({ token, query: undefined }),
    );
    mockedGet.mock.calls.slice(1).forEach(([, options]) => {
      expect(options?.query).toEqual({ search: 'Tool', q: 'Tool', external: 'true' });
    });
  });

  it('omits external catalog parameters when no query is provided', async () => {
    await fetchAllCatalogResources(token, '');

    expect(mockedGet).toHaveBeenCalledTimes(4);
    mockedGet.mock.calls.forEach(([, options]) => {
      expect(options?.query).toBeUndefined();
    });
  });

  it('returns partial results when one resource request fails', async () => {
    mockedGet
      .mockResolvedValueOnce({ results: [{ id: 1, name: 'tool metal', spotify_id: 'genre-1' }] })
      .mockResolvedValueOnce({ results: [{ id: 2, name: 'Album', spotify_id: 'alb-1', artists: [], total_tracks: 10, release_date: '2020-01-01' }] })
      .mockRejectedValueOnce(new Error('artists failed'))
      .mockResolvedValueOnce({ results: [{ id: 4, name: 'Track', spotify_id: 'trk-1', album: null, duration_ms: 1000, track_number: 1, explicit: false }] });

    const payload = await fetchAllCatalogResources(token, 'Tool');

    expect(payload.genres).toHaveLength(1);
    expect(payload.albums).toHaveLength(1);
    expect(payload.artists).toHaveLength(0);
    expect(payload.tracks).toHaveLength(1);
  });

  it('fetches album detail by spotify id through external endpoint', async () => {
    mockedGet.mockResolvedValueOnce({ id: 42, name: 'Around the Fur', spotify_id: '4o1c5YdNwQ8b8fpkR6r6E9' });

    await fetchAlbumDetailBySpotifyId(token, '4o1c5YdNwQ8b8fpkR6r6E9');

    expect(mockedGet).toHaveBeenCalledWith(
      '/api/v1/albums/4o1c5YdNwQ8b8fpkR6r6E9/',
      expect.objectContaining({
        token,
        query: { external: 'true' },
      }),
    );
  });
});
