import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useAuth } from '../../auth/hooks/useAuth';
import type { Track } from '../../catalog/types';
import type { PlaybackProviderName, PlaybackState } from '../types';
import type { PlayRequest } from '../api/playbackApi';
import { fetchPlaybackState, nextTrack, pausePlayback, previousTrack, seekPlayback, startPlayback } from '../api/playbackApi';
import { deriveTrackUri } from '../utils';

export type PlaybackContextValue = {
  state: PlaybackState | null;
  error: string | null;
  isBusy: boolean;
  isPlaying: boolean;
  canControl: boolean;
  activeTrackUri: string | null;
  playTrack: (
    track: Track,
    overrides?: { provider?: PlaybackProviderName; contextUri?: string | null },
  ) => Promise<void>;
  playContext: (contextUri: string, overrides?: { provider?: PlaybackProviderName }) => Promise<void>;
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  next: () => Promise<void>;
  previous: () => Promise<void>;
  seek: (positionMs: number) => Promise<void>;
  refresh: () => Promise<void>;
};

const PlaybackContext = createContext<PlaybackContextValue | undefined>(undefined);

const DEFAULT_PROVIDER: PlaybackProviderName = 'spotify';
const PLAYBACK_SYNC_DELAY_MS = 900;
const PLAYBACK_POLL_WHILE_PLAYING_MS = 6000;
const PLAYBACK_POLL_IDLE_MS = 12000;

export const buildTrackPlaybackRequest = (
  provider: PlaybackProviderName,
  trackUri: string,
  contextUri?: string | null,
): PlayRequest => {
  if (contextUri) {
    return {
      provider,
      context_uri: contextUri,
      offset_uri: trackUri,
    };
  }
  return {
    provider,
    track_uri: trackUri,
  };
};

const getFirstArtwork = (images?: unknown) => {
  if (!Array.isArray(images)) {
    return null;
  }
  const first = images.find((image) => typeof image === 'string' && image.trim().length > 0);
  return typeof first === 'string' ? first : null;
};

const normalizeOptimisticTrack = (track: Track) => {
  const album = typeof track.album === 'object' && track.album !== null ? track.album : null;
  const albumArtists = Array.isArray(album?.artists) ? album.artists : [];
  const artists = albumArtists.reduce<Array<{ id?: string; uri?: string; name?: string }>>((acc, artist) => {
    if (typeof artist === 'object' && artist !== null && 'spotify_id' in artist && 'name' in artist) {
      const spotifyId = (artist as { spotify_id?: unknown }).spotify_id;
      const name = (artist as { name?: unknown }).name;
      acc.push({
        id: typeof spotifyId === 'string' ? spotifyId : undefined,
        uri: typeof spotifyId === 'string' ? `spotify:artist:${spotifyId}` : undefined,
        name: typeof name === 'string' ? name : undefined,
      });
    }
    return acc;
  }, []);
  const trackArtwork = getFirstArtwork(track.spotify_data?.images);
  const albumArtwork = getFirstArtwork(album?.spotify_data?.images);
  const trackUri = deriveTrackUri(track);

  return {
    id: track.spotify_id,
    uri: trackUri,
    name: track.name,
    duration_ms: track.duration_ms,
    artwork_url: trackArtwork ?? albumArtwork,
    artists,
    album: album
      ? {
          id: album.spotify_id,
          uri: `spotify:album:${album.spotify_id}`,
          name: album.name,
          artwork_url: albumArtwork,
        }
      : null,
  };
};

export const PlaybackProvider = ({ children }: { children: ReactNode }) => {
  const { token } = useAuth();
  const [state, setState] = useState<PlaybackState | null>(null);
  const [activeProvider, setActiveProvider] = useState<PlaybackProviderName>(DEFAULT_PROVIDER);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const canControl = Boolean(token);
  const activeTrackUri = state?.track?.uri ?? null;
  const isPlaying = Boolean(state?.is_playing);

  const applyState = useCallback(
    (next: PlaybackState | null) => {
      setState(next);
      if (next?.provider) {
        setActiveProvider(next.provider);
      }
    },
    [],
  );

  const runAction = useCallback(
    async (operation: () => Promise<PlaybackState | null>, options?: { silent?: boolean; preserveLocalState?: boolean }) => {
      if (!token) {
        throw new Error('Playback actions require authentication.');
      }
      if (!options?.silent) {
        setIsBusy(true);
      }
      try {
        const payload = await operation();
        setError(null);
        if (!options?.preserveLocalState) {
          applyState(payload);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Unable to control playback.';
        setError(message);
        throw err;
      } finally {
        if (!options?.silent) {
          setIsBusy(false);
        }
      }
    },
    [applyState, token],
  );

  const ensureAuthenticated = useCallback(() => {
    if (token) {
      return true;
    }
    setError('Sign in to control playback.');
    return false;
  }, [token]);

  const refresh = useCallback(async () => {
    if (!token) {
      applyState(null);
      setError(null);
      return;
    }
    try {
      await runAction(() => fetchPlaybackState(token, state?.provider ?? activeProvider), { silent: true });
    } catch {
      // errors are surfaced through setError already
    }
  }, [activeProvider, applyState, runAction, state?.provider, token]);

  const refreshSoon = useCallback(() => {
    window.setTimeout(() => {
      void refresh();
    }, PLAYBACK_SYNC_DELAY_MS);
  }, [refresh]);

  const playTrack = useCallback(
    async (track: Track, overrides?: { provider?: PlaybackProviderName; contextUri?: string | null }) => {
      const uri = deriveTrackUri(track);
      if (!uri) {
        setError('This track is missing a playable Spotify reference.');
        return;
      }
      if (!ensureAuthenticated() || !token) {
        return;
      }
      const provider = overrides?.provider ?? state?.provider ?? activeProvider ?? DEFAULT_PROVIDER;
      const normalizedContextUri = overrides?.contextUri?.trim() || null;
      const previousState = state;
      setActiveProvider(provider);
      applyState({
        provider,
        is_playing: true,
        progress_ms: 0,
        updated_at: new Date().toISOString(),
        device: state?.device ?? null,
        track: normalizeOptimisticTrack(track),
      });
      try {
        await runAction(
          () =>
            startPlayback(token, buildTrackPlaybackRequest(provider, uri, normalizedContextUri)),
          { silent: false, preserveLocalState: true },
        );
        refreshSoon();
      } catch {
        applyState(previousState ?? null);
      }
    },
    [activeProvider, applyState, ensureAuthenticated, refreshSoon, runAction, state, token],
  );

  const playContext = useCallback(
    async (contextUri: string, overrides?: { provider?: PlaybackProviderName }) => {
      const normalizedContextUri = contextUri.trim();
      if (!normalizedContextUri) {
        setError('Missing playback context.');
        return;
      }
      if (!ensureAuthenticated() || !token) {
        return;
      }
      const provider = overrides?.provider ?? state?.provider ?? activeProvider ?? DEFAULT_PROVIDER;
      const previousState = state;
      setActiveProvider(provider);
      applyState({
        provider,
        is_playing: true,
        progress_ms: 0,
        updated_at: new Date().toISOString(),
        device: state?.device ?? null,
        track: null,
      });
      try {
        await runAction(() => startPlayback(token, { provider, context_uri: normalizedContextUri }), {
          silent: false,
          preserveLocalState: true,
        });
        refreshSoon();
      } catch {
        applyState(previousState ?? null);
      }
    },
    [activeProvider, applyState, ensureAuthenticated, refreshSoon, runAction, state, token],
  );

  const pause = useCallback(async () => {
    if (!ensureAuthenticated() || !token) {
      return;
    }
    const provider = state?.provider ?? activeProvider;
    const deviceId = state?.device?.id ?? undefined;
    try {
      await runAction(() => pausePlayback(token, { provider, device_id: deviceId }), { silent: false });
      refreshSoon();
    } catch {
      // handled globally
    }
  }, [activeProvider, ensureAuthenticated, refreshSoon, runAction, state?.device?.id, state?.provider, token]);

  const resume = useCallback(async () => {
    if (!ensureAuthenticated() || !token) {
      return;
    }
    const provider = state?.provider ?? activeProvider;
    const deviceId = state?.device?.id ?? undefined;
    try {
      await runAction(
        () =>
          startPlayback(token, {
            provider,
            device_id: deviceId,
          }),
        { silent: false },
      );
      refreshSoon();
    } catch {
      // handled globally
    }
  }, [activeProvider, ensureAuthenticated, refreshSoon, runAction, state?.device?.id, state?.provider, token]);

  const next = useCallback(async () => {
    if (!ensureAuthenticated() || !token) {
      return;
    }
    const provider = state?.provider ?? activeProvider;
    const deviceId = state?.device?.id ?? undefined;
    try {
      await runAction(() => nextTrack(token, { provider, device_id: deviceId }), { silent: false });
      refreshSoon();
    } catch {
      // handled globally
    }
  }, [activeProvider, ensureAuthenticated, refreshSoon, runAction, state?.device?.id, state?.provider, token]);

  const previous = useCallback(async () => {
    if (!ensureAuthenticated() || !token) {
      return;
    }
    const provider = state?.provider ?? activeProvider;
    const deviceId = state?.device?.id ?? undefined;
    try {
      await runAction(() => previousTrack(token, { provider, device_id: deviceId }), { silent: false });
      refreshSoon();
    } catch {
      // handled globally
    }
  }, [activeProvider, ensureAuthenticated, refreshSoon, runAction, state?.device?.id, state?.provider, token]);

  const seek = useCallback(async (positionMs: number) => {
    if (!ensureAuthenticated() || !token) {
      return;
    }
    const provider = state?.provider ?? activeProvider;
    const deviceId = state?.device?.id ?? undefined;
    const normalizedPosition = Math.max(0, Math.round(positionMs));
    try {
      await runAction(
        () => seekPlayback(token, { provider, device_id: deviceId, position_ms: normalizedPosition }),
        { silent: false },
      );
      refreshSoon();
    } catch {
      // handled globally
    }
  }, [activeProvider, ensureAuthenticated, refreshSoon, runAction, state?.device?.id, state?.provider, token]);

  useEffect(() => {
    if (!token) {
      applyState(null);
      setIsBusy(false);
      return;
    }
    void refresh();
  }, [applyState, refresh, token]);

  useEffect(() => {
    if (!state?.is_playing) {
      return undefined;
    }
    const interval = window.setInterval(() => {
      setState((prev) => {
        if (!prev?.is_playing) {
          return prev;
        }
        const duration = typeof prev.track?.duration_ms === 'number' ? prev.track.duration_ms : Number.MAX_SAFE_INTEGER;
        const currentProgress = typeof prev.progress_ms === 'number' ? prev.progress_ms : 0;
        const nextProgress = Math.min(currentProgress + 1000, duration);
        return { ...prev, progress_ms: nextProgress };
      });
    }, 1000);
    return () => window.clearInterval(interval);
  }, [state?.is_playing]);

  useEffect(() => {
    if (!token) {
      return undefined;
    }
    const intervalMs = state?.is_playing ? PLAYBACK_POLL_WHILE_PLAYING_MS : PLAYBACK_POLL_IDLE_MS;
    const interval = window.setInterval(() => {
      void refresh();
    }, intervalMs);
    return () => window.clearInterval(interval);
  }, [refresh, state?.is_playing, token]);

  useEffect(() => {
    if (!token) {
      return undefined;
    }

    const refreshFromSystemPlayback = () => {
      void refresh();
    };

    window.addEventListener('focus', refreshFromSystemPlayback);
    document.addEventListener('visibilitychange', refreshFromSystemPlayback);

    return () => {
      window.removeEventListener('focus', refreshFromSystemPlayback);
      document.removeEventListener('visibilitychange', refreshFromSystemPlayback);
    };
  }, [refresh, token]);

  const value = useMemo<PlaybackContextValue>(
    () => ({
      state,
      error,
      isBusy,
      isPlaying,
      canControl,
      activeTrackUri,
      playTrack,
      playContext,
      pause,
      resume,
      next,
      previous,
      seek,
      refresh,
    }),
    [activeTrackUri, canControl, error, isBusy, isPlaying, next, pause, playContext, playTrack, previous, refresh, resume, seek, state],
  );

  return <PlaybackContext.Provider value={value}>{children}</PlaybackContext.Provider>;
};

export const usePlaybackContext = () => {
  const ctx = useContext(PlaybackContext);
  if (!ctx) {
    throw new Error('usePlayback must be used within PlaybackProvider');
  }
  return ctx;
};
