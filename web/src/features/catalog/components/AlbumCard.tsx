import type { Album, Artist } from '../types';
import { formatReleaseDate } from '@shared/utils/formatters';

const extractArtistName = (artist: Artist | string | number | undefined | null): string | null => {
  if (!artist) {
    return null;
  }
  if (typeof artist === 'string') {
    try {
      const url = new URL(artist);
      const segments = url.pathname.split('/').filter(Boolean);
      const maybeId = segments.length > 0 ? segments[segments.length - 1] : undefined;
      return maybeId ? `Artist ${maybeId}` : artist;
    } catch {
      return artist;
    }
  }
  if (typeof artist === 'number') {
    return `Artist ${artist}`;
  }
  return artist.name;
};

const AlbumCard = ({ album }: { album: Album }) => {
  const artistNames = Array.isArray(album.artists)
    ? album.artists
        .map((artist) => extractArtistName(artist))
        .filter((name): name is string => Boolean(name))
    : [];

  const subtitle = artistNames.length ? artistNames.join(', ') : 'Unknown artist';

  return (
    <article className="card card--compact">
      <h4>{album.name}</h4>
      <p className="muted">
        {subtitle} • {formatReleaseDate(album.release_date)}
      </p>
      <p className="stats">{album.total_tracks} tracks</p>
    </article>
  );
};

export default AlbumCard;
