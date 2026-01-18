import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';
import { fetchAllCatalogResources } from './catalogApi';
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

    expect(mockedGet).toHaveBeenCalledTimes(3);
    mockedGet.mock.calls.forEach(([, options]) => {
      expect(options?.query).toEqual({ search: 'Tool', q: 'Tool', external: 'true' });
    });
  });

  it('omits external catalog parameters when no query is provided', async () => {
    await fetchAllCatalogResources(token, '');

    expect(mockedGet).toHaveBeenCalledTimes(3);
    mockedGet.mock.calls.forEach(([, options]) => {
      expect(options?.query).toBeUndefined();
    });
  });
});
