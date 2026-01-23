export type GlobePoint = {
  id: number;
  username: string;
  lat: number;
  lng: number;
  clout: number;
  top_genre: string;
  display_name: string;
};

export type UserDetail = {
  id: number;
  username: string;
  display_name: string;
  avatar_url: string;
  tagline: string;
  location: string;
  clout: number;
  top_genre: string;
  favorite_genres: string[];
  favorite_artists: string[];
  favorite_albums: string[];
  favorite_tracks: string[];
};
