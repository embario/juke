export type MusicProfile = {
  id: number;
  username: string;
  name: string | null;
  display_name: string;
  tagline: string;
  bio: string;
  location: string;
  avatar_url: string;
  favorite_genres: string[];
  favorite_artists: string[];
  favorite_albums: string[];
  favorite_tracks: string[];
  created_at: string;
  modified_at: string;
  is_owner: boolean;
};

export type MusicProfileUpdatePayload = Partial<
  Pick<
    MusicProfile,
    |
      'display_name'
      | 'tagline'
      | 'bio'
      | 'location'
      | 'avatar_url'
      | 'favorite_genres'
      | 'favorite_artists'
      | 'favorite_albums'
      | 'favorite_tracks'
  >
> & {
  name?: string | null;
};

export type MusicProfileSearchResult = {
  username: string;
  display_name: string;
  tagline: string;
  avatar_url: string;
};
