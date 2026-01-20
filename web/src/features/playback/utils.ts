import type { Track } from '../catalog/types';

const SPOTIFY_TRACK_PREFIX = 'spotify:track:';

export const deriveTrackUri = (track: Track | null | undefined): string | null => {
  if (!track) {
    return null;
  }

  const spotifyDataUri = track.spotify_data?.uri;
  if (typeof spotifyDataUri === 'string' && spotifyDataUri.trim()) {
    return spotifyDataUri.trim();
  }

  const candidate = track.spotify_id;
  if (!candidate) {
    return null;
  }

  if (candidate.startsWith('spotify:')) {
    return candidate;
  }

  return `${SPOTIFY_TRACK_PREFIX}${candidate}`;
};

export const hasPlayableUri = (track: Track | null | undefined): boolean => Boolean(deriveTrackUri(track));
