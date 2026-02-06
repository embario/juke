import apiClient from '@shared/api/apiClient';
import type { SearchHistoryPayload } from '../types';

export const createSearchHistory = async (token: string, payload: SearchHistoryPayload) => {
  return apiClient.post('/api/v1/search-history/', payload, { token });
};

export default createSearchHistory;
