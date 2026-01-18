export type SpotifyData = {
  images?: string[];
  [key: string]: unknown;
};

type BaseResource = {
  id?: number;
  url?: string;
  spotify_id: string;
  spotify_data?: SpotifyData;
  custom_data?: Record<string, unknown>;
};

export type Genre = BaseResource & {
  name: string;
};

export type Artist = BaseResource & {
  name: string;
  genres?: Array<string | Genre>;
};

export type Album = BaseResource & {
  name: string;
  artists?: Array<Artist | string | number>;
  total_tracks: number;
  release_date: string;
};

export type Track = BaseResource & {
  name: string;
  album: Album | number | string | null;
  duration_ms: number;
  track_number: number;
  explicit: boolean;
};

export type CatalogResults = {
  genres: Genre[];
  artists: Artist[];
  albums: Album[];
  tracks: Track[];
};

export type CatalogFilter = 'albums' | 'artists' | 'tracks';
