import type { ReactNode } from 'react';
import { formatDuration } from '@shared/utils/formatters';
import usePlayback from '../hooks/usePlayback';

const artistLine = (names?: (string | undefined)[]) => names?.filter(Boolean).join(', ') || '—';

const ControlButton = ({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled: boolean; children: ReactNode }) => (
  <button type="button" className="playback-dock__control" onClick={onClick} aria-label={label} disabled={disabled}>
    {children}
  </button>
);

const PlaybackBar = () => {
  const { state, error, isBusy, isPlaying, canControl, pause, resume, next, previous } = usePlayback();
  const track = state?.track;
  const progressMs = state?.progress_ms ?? 0;
  const durationMs = track?.duration_ms ?? 0;
  const progressPercent = durationMs > 0 ? Math.min(100, Math.round((progressMs / durationMs) * 100)) : 0;
  const playbackDisabled = !canControl || (!track && !isPlaying);
  const artwork = track?.artwork_url;
  const artistNames = track?.artists?.map((artist) => artist.name);

  const handleToggle = () => {
    if (!canControl) {
      return;
    }
    if (isPlaying) {
      void pause();
    } else if (track) {
      void resume();
    }
  };

  const handleNext = () => {
    if (!canControl) {
      return;
    }
    void next();
  };

  const handlePrevious = () => {
    if (!canControl) {
      return;
    }
    void previous();
  };

  const playbackMessage = !canControl
    ? 'Sign in with Spotify to control playback.'
    : 'Select a track to start listening.';

  return (
    <footer className="playback-dock">
      <div className="playback-dock__panel">
        {track ? (
          <div className="playback-dock__meta">
            <div className="playback-dock__artwork" aria-hidden={!artwork}>
              {artwork ? (
                <img src={artwork} alt={`${track.name ?? 'Track'} artwork`} />
              ) : (
                <span>{(track.name ?? '♪').charAt(0)}</span>
              )}
            </div>
            <div className="playback-dock__details">
              <p className="playback-dock__title">{track.name ?? 'Unknown track'}</p>
              <p className="playback-dock__subtitle">{artistLine(artistNames)}</p>
            </div>
          </div>
        ) : (
          <div className="playback-dock__meta playback-dock__meta--empty">
            <p>{playbackMessage}</p>
          </div>
        )}
        <div className="playback-dock__controls">
          <div className="playback-dock__buttons">
            <ControlButton label="Previous track" onClick={handlePrevious} disabled={playbackDisabled || isBusy}>
              <svg viewBox="0 0 24 24" role="presentation">
                <path d="M6 5v14h2V5H6zm3 7 9 7V5l-9 7z" />
              </svg>
            </ControlButton>
            <ControlButton
              label={isPlaying ? 'Pause playback' : 'Resume playback'}
              onClick={handleToggle}
              disabled={!canControl || isBusy || (!track && !state)}
            >
              {isPlaying ? (
                <svg viewBox="0 0 24 24" role="presentation">
                  <path d="M8 5h3v14H8zm5 0h3v14h-3z" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" role="presentation">
                  <path d="M8 5v14l11-7z" />
                </svg>
              )}
            </ControlButton>
            <ControlButton label="Next track" onClick={handleNext} disabled={playbackDisabled || isBusy}>
              <svg viewBox="0 0 24 24" role="presentation">
                <path d="M16 5v14h2V5h-2zm-9 7 9 7V5l-9 7z" />
              </svg>
            </ControlButton>
          </div>
          <div className="playback-dock__progress" aria-live="polite">
            <span>{formatDuration(progressMs)}</span>
            <div className="playback-dock__progress-track">
              <div className="playback-dock__progress-bar" style={{ width: `${progressPercent}%` }} />
            </div>
            <span>{durationMs ? formatDuration(durationMs) : '0:00'}</span>
          </div>
        </div>
        <div className="playback-dock__status">
          <p className="playback-dock__device">{state?.device?.name ?? 'No active device'}</p>
          <p className="playback-dock__provider">{(state?.provider ?? 'spotify').toUpperCase()}</p>
          {error ? <p className="playback-dock__error" role="status">{error}</p> : null}
          {isBusy ? <span className="playback-dock__spinner" aria-live="polite" /> : null}
        </div>
      </div>
    </footer>
  );
};

export default PlaybackBar;
