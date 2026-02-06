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

export type GenreDetail = Genre & {
  description?: string;
  top_artists: Artist[];
};

export type ArtistDetail = Omit<Artist, 'genres'> & {
  bio?: string;
  albums: Album[];
  top_tracks: Track[];
  related_artists: Artist[];
  genres: Genre[];
};

export type AlbumDetail = Album & {
  description?: string;
  tracks: Track[];
  related_albums: Album[];
};

export type CatalogFilter = 'genres' | 'albums' | 'artists' | 'tracks';
export type CatalogResourceType = 'genre' | 'artist' | 'album' | 'track';
export type NavigationResourceType = 'search' | 'genre' | 'artist' | 'album';

export type NavigationStackItem = {
  resourceType: NavigationResourceType;
  label: string;
  resourceId?: number;
  searchQuery?: string;
};

export type SearchHistoryResourcePayload = {
  resource_type: CatalogResourceType;
  resource_id: number;
  resource_name: string;
};

export type SearchHistoryPayload = {
  search_query: string;
  engaged_resources: SearchHistoryResourcePayload[];
};
