import type { Artist } from '../types';

const getArtistArtwork = (artist: Artist): string | null => {
  const images = artist.spotify_data?.images;
  if (Array.isArray(images) && images.length > 0) {
    const firstImage = images.find((image) => Boolean(image));
    if (typeof firstImage === 'string') {
      return firstImage;
    }
  }
  const customImage = artist.custom_data?.['image_url'];
  return typeof customImage === 'string' ? customImage : null;
};

const ArtistCard = ({ artist }: { artist: Artist }) => {
  const genreLabels = Array.isArray(artist.genres)
    ? artist.genres.map((genre) => (typeof genre === 'string' ? genre : genre.name))
    : [];

  const subtitle = genreLabels.length ? genreLabels.join(', ') : 'Genres unavailable';
  const artworkUrl = getArtistArtwork(artist);
  const thumbnailLabel = `${artist.name} artwork`;
  const fallbackGlyph = artist.name?.charAt(0)?.toUpperCase() ?? '♪';

  return (
    <article className="card card--compact media-card">
      <div
        className="media-card__thumb"
        role={artworkUrl ? undefined : 'img'}
        aria-label={artworkUrl ? undefined : thumbnailLabel}
      >
        {artworkUrl ? <img src={artworkUrl} alt={thumbnailLabel} loading="lazy" /> : <span aria-hidden="true">{fallbackGlyph}</span>}
      </div>
      <div className="media-card__content">
        <h4>{artist.name}</h4>
        <p className="muted">{subtitle}</p>
      </div>
    </article>
  );
};

export default ArtistCard;
