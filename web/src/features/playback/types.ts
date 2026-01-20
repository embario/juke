import type { Track } from '../catalog/types';

export type PlaybackProviderName = 'spotify' | string;

export type PlaybackArtist = {
  id?: string | null;
  uri?: string | null;
  name?: string;
};

export type PlaybackAlbum = {
  id?: string | null;
  uri?: string | null;
  name?: string;
  artwork_url?: string | null;
};

export type PlaybackTrack = {
  id?: string | null;
  uri?: string | null;
  name?: string;
  duration_ms?: number | null;
  artwork_url?: string | null;
  album?: PlaybackAlbum | null;
  artists?: PlaybackArtist[];
};

export type PlaybackDevice = {
  id?: string | null;
  name?: string | null;
  type?: string | null;
  volume_percent?: number | null;
  is_active?: boolean | null;
};

export type PlaybackState = {
  provider: PlaybackProviderName;
  is_playing: boolean;
  progress_ms: number;
  track?: PlaybackTrack | null;
  device?: PlaybackDevice | null;
  updated_at?: string;
};

export type PlaybackTarget = {
  provider?: PlaybackProviderName;
  track?: Track;
  uri?: string | null;
};
