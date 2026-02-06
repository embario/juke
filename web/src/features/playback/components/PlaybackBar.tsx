import { useState, type KeyboardEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { formatDuration } from '@shared/utils/formatters';
import usePlayback from '../hooks/usePlayback';

const ControlButton = ({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled: boolean; children: ReactNode }) => (
  <button type="button" className="playback-dock__control" onClick={onClick} aria-label={label} disabled={disabled}>
    {children}
  </button>
);

const extractSpotifyId = (value?: string | null) => {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  if (trimmed.startsWith('spotify:')) {
    const segments = trimmed.split(':');
    return segments[segments.length - 1] || null;
  }

  const slashSegments = trimmed.split('/');
  return slashSegments[slashSegments.length - 1] || trimmed;
};

const buildDetailLink = (resourceType: 'artist' | 'album', spotifyId?: string | null) => {
  if (!spotifyId) {
    return null;
  }
  return `/?open=${resourceType}&sid=${encodeURIComponent(spotifyId)}`;
};

type ScrubState = {
  trackUri: string | null;
  value: number | null;
  isScrubbing: boolean;
};

const PlaybackBar = () => {
  const { state, error, isBusy, isPlaying, canControl, pause, resume, next, previous, seek } = usePlayback();
  const track = state?.track;
  const trackUri = track?.uri ?? null;
  const progressMs = state?.progress_ms ?? 0;
  const durationMs = track?.duration_ms ?? 0;
  const [scrubState, setScrubState] = useState<ScrubState>({
    trackUri: null,
    value: null,
    isScrubbing: false,
  });
  const activeScrubState = scrubState.trackUri === trackUri
    ? scrubState
    : { trackUri, value: null, isScrubbing: false };
  const scrubValue = activeScrubState.value;
  const isScrubbing = activeScrubState.isScrubbing;
  const displayedProgressMs = isScrubbing && scrubValue !== null ? scrubValue : progressMs;
  const progressPercent = durationMs > 0 ? Math.min(100, Math.round((displayedProgressMs / durationMs) * 100)) : 0;
  const playbackDisabled = !canControl || (!track && !isPlaying);
  const scrubDisabled = !canControl || !track || isBusy || durationMs <= 0;
  const artwork = track?.artwork_url;
  const albumSpotifyId = extractSpotifyId(track?.album?.id) ?? extractSpotifyId(track?.album?.uri);
  const albumDetailLink = buildDetailLink('album', albumSpotifyId);
  const albumName = track?.album?.name ?? 'Unknown album';
  const trackDetailLink = albumDetailLink;
  const artistLinks = (track?.artists ?? []).map((artist) => {
    const spotifyId = extractSpotifyId(artist.id) ?? extractSpotifyId(artist.uri);
    return {
      name: artist.name ?? 'Unknown artist',
      href: buildDetailLink('artist', spotifyId),
    };
  });

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

  const commitScrub = (value: number | null) => {
    if (!track || durationMs <= 0 || value === null) {
      setScrubState({ trackUri, value: null, isScrubbing: false });
      return;
    }
    const bounded = Math.max(0, Math.min(durationMs, value));
    setScrubState({ trackUri, value: null, isScrubbing: false });
    void seek(bounded);
  };

  const handleScrubKeyUp = (event: KeyboardEvent<HTMLInputElement>) => {
    const key = event.key;
    if (key === 'ArrowLeft' || key === 'ArrowRight' || key === 'Home' || key === 'End' || key === 'PageUp' || key === 'PageDown') {
      const value = Number(event.currentTarget.value);
      commitScrub(Number.isFinite(value) ? value : null);
    }
  };

  const playbackMessage = !canControl
    ? 'Sign in with Spotify to control playback.'
    : 'Select a track to start listening.';

  return (
    <footer className="playback-dock">
      <div className="playback-dock__panel">
        {track ? (
          <div className="playback-dock__meta">
            {albumDetailLink ? (
              <Link to={albumDetailLink} className="playback-dock__artwork-link" aria-label={`Open ${albumName} detail`}>
                <div className="playback-dock__artwork" aria-hidden={!artwork}>
                  {artwork ? (
                    <img src={artwork} alt={`${track.name ?? 'Track'} artwork`} />
                  ) : (
                    <span>{(track.name ?? '♪').charAt(0)}</span>
                  )}
                </div>
              </Link>
            ) : (
              <div className="playback-dock__artwork" aria-hidden={!artwork}>
                {artwork ? (
                  <img src={artwork} alt={`${track.name ?? 'Track'} artwork`} />
                ) : (
                  <span>{(track.name ?? '♪').charAt(0)}</span>
                )}
              </div>
            )}
            <div className="playback-dock__details">
              <p className="playback-dock__title">
                {trackDetailLink ? (
                  <Link to={trackDetailLink} className="playback-dock__link" title="Open album detail">
                    {track.name ?? 'Unknown track'}
                  </Link>
                ) : (
                  track.name ?? 'Unknown track'
                )}
              </p>
              <p className="playback-dock__subtitle">
                {artistLinks.length > 0 ? (
                  artistLinks.map((artist, index) => (
                    <span key={`${artist.name}-${index}`}>
                      {artist.href ? (
                        <Link to={artist.href} className="playback-dock__link">
                          {artist.name}
                        </Link>
                      ) : (
                        artist.name
                      )}
                      {index < artistLinks.length - 1 ? ', ' : ''}
                    </span>
                  ))
                ) : (
                  '—'
                )}
              </p>
              <p className="playback-dock__subtitle playback-dock__subtitle--album">
                Album:{' '}
                {albumDetailLink ? (
                  <Link to={albumDetailLink} className="playback-dock__link">
                    {albumName}
                  </Link>
                ) : (
                  albumName
                )}
              </p>
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
            <span>{formatDuration(displayedProgressMs)}</span>
            <div className="playback-dock__progress-track">
              <div className="playback-dock__progress-bar" style={{ width: `${progressPercent}%` }} />
              <input
                type="range"
                min={0}
                max={Math.max(durationMs, 0)}
                step={1000}
                value={isScrubbing && scrubValue !== null ? scrubValue : (durationMs > 0 ? Math.max(Math.min(progressMs, durationMs), 0) : 0)}
                className="playback-dock__scrubber"
                aria-label="Scrub playback position"
                disabled={scrubDisabled}
                onPointerDown={() => {
                  if (!scrubDisabled) {
                    setScrubState({ trackUri, value: progressMs, isScrubbing: true });
                  }
                }}
                onChange={(event) => {
                  const nextValue = Number(event.currentTarget.value);
                  if (!Number.isFinite(nextValue)) {
                    return;
                  }
                  setScrubState({ trackUri, value: nextValue, isScrubbing: true });
                }}
                onPointerUp={(event) => {
                  const nextValue = Number(event.currentTarget.value);
                  commitScrub(Number.isFinite(nextValue) ? nextValue : scrubValue);
                }}
                onKeyUp={handleScrubKeyUp}
              />
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
