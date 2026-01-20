import clsx from 'clsx';
import type { Track } from '../types';
import { formatDuration } from '@shared/utils/formatters';

type Props = {
  track: Track;
  artworkUrl?: string;
  onPlay?: (track: Track) => void;
  isActive?: boolean;
  isPlaying?: boolean;
  isDisabled?: boolean;
  isLoading?: boolean;
};

const TrackCard = ({ track, artworkUrl, onPlay, isActive = false, isPlaying = false, isDisabled = false, isLoading = false }: Props) => {
  const thumbnailLabel = `${track.name} artwork`;
  const fallbackGlyph = track.name?.charAt(0)?.toUpperCase() ?? '♪';
  const canPlay = Boolean(onPlay) && !isDisabled;

  const handlePlay = () => {
    if (!canPlay || !onPlay) {
      return;
    }
    onPlay(track);
  };

  return (
    <button
      type="button"
      className={clsx('card', 'card--compact', 'media-card', 'track-card', canPlay && 'track-card--interactive', isActive && 'track-card--active')}
      onClick={handlePlay}
      disabled={!canPlay}
      aria-pressed={isActive}
      aria-label={canPlay ? `Play ${track.name}` : track.name}
    >
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
      <div className="track-card__actions" aria-hidden={!canPlay}>
        {isLoading ? (
          <span className="track-card__spinner" />
        ) : (
          <svg viewBox="0 0 24 24" role="presentation">
            {isActive && isPlaying ? <path d="M7 5h4v14H7zm6 0h4v14h-4z" /> : <path d="M8 5v14l11-7z" />}
          </svg>
        )}
      </div>
    </button>
  );
};

export default TrackCard;
