import type { Track } from '../types';
import { formatDuration } from '@shared/utils/formatters';

type Props = {
  track: Track;
  artworkUrl?: string;
};

const TrackCard = ({ track, artworkUrl }: Props) => {
  const thumbnailLabel = `${track.name} artwork`;
  const fallbackGlyph = track.name?.charAt(0)?.toUpperCase() ?? '♪';

  return (
    <article className="card card--compact media-card track-card">
      <div
        className="media-card__thumb"
        role={artworkUrl ? undefined : 'img'}
        aria-label={artworkUrl ? undefined : thumbnailLabel}
      >
        {artworkUrl ? <img src={artworkUrl} alt={thumbnailLabel} loading="lazy" /> : <span aria-hidden="true">{fallbackGlyph}</span>}
      </div>
      <div className="media-card__content">
        <div className="media-card__row">
          <h4>{track.name}</h4>
          <span className="muted">{formatDuration(track.duration_ms)}</span>
        </div>
        <p className="muted">Track {track.track_number}</p>
      </div>
    </article>
  );
};

export default TrackCard;
