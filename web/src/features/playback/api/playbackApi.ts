import apiClient from '@shared/api/apiClient';
import type { PlaybackState } from '../types';

export type PlayRequest = {
  provider?: string;
  track_uri?: string;
  context_uri?: string;
  position_ms?: number;
  device_id?: string;
};

export type ControlRequest = {
  provider?: string;
  device_id?: string;
};

type PlaybackStateResponse = PlaybackState | Record<string, never> | null;

const unwrapState = (payload: PlaybackStateResponse): PlaybackState | null => {
  if (!payload) {
    return null;
  }
  return 'provider' in payload ? (payload as PlaybackState) : null;
};

export const startPlayback = async (token: string, body: PlayRequest) => {
  const response = await apiClient.post<PlaybackStateResponse>('/api/v1/playback/play/', body, { token });
  return unwrapState(response);
};

export const pausePlayback = async (token: string, body: ControlRequest = {}) => {
  const response = await apiClient.post<PlaybackStateResponse>('/api/v1/playback/pause/', body, { token });
  return unwrapState(response);
};

export const nextTrack = async (token: string, body: ControlRequest = {}) => {
  const response = await apiClient.post<PlaybackStateResponse>('/api/v1/playback/next/', body, { token });
  return unwrapState(response);
};

export const previousTrack = async (token: string, body: ControlRequest = {}) => {
  const response = await apiClient.post<PlaybackStateResponse>('/api/v1/playback/previous/', body, { token });
  return unwrapState(response);
};

export const fetchPlaybackState = async (token: string, provider?: string) => {
  const query = provider ? { provider } : undefined;
  const response = await apiClient.get<PlaybackStateResponse>('/api/v1/playback/state/', { token, query });
  return unwrapState(response);
};
