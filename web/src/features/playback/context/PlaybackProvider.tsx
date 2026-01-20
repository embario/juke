import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useAuth } from '../../auth/hooks/useAuth';
import type { Track } from '../../catalog/types';
import type { PlaybackProviderName, PlaybackState } from '../types';
import { fetchPlaybackState, nextTrack, pausePlayback, previousTrack, startPlayback } from '../api/playbackApi';
import { deriveTrackUri } from '../utils';

export type PlaybackContextValue = {
  state: PlaybackState | null;
  error: string | null;
  isBusy: boolean;
  isPlaying: boolean;
  canControl: boolean;
  activeTrackUri: string | null;
  playTrack: (track: Track, overrides?: { provider?: PlaybackProviderName }) => Promise<void>;
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  next: () => Promise<void>;
  previous: () => Promise<void>;
  refresh: () => Promise<void>;
};

const PlaybackContext = createContext<PlaybackContextValue | undefined>(undefined);

const DEFAULT_PROVIDER: PlaybackProviderName = 'spotify';

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
    async (operation: () => Promise<PlaybackState | null>, options?: { silent?: boolean }) => {
      if (!token) {
        throw new Error('Playback actions require authentication.');
      }
      if (!options?.silent) {
        setIsBusy(true);
      }
      try {
        const payload = await operation();
        setError(null);
        applyState(payload);
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

  const playTrack = useCallback(
    async (track: Track, overrides?: { provider?: PlaybackProviderName }) => {
      const uri = deriveTrackUri(track);
      if (!uri) {
        setError('This track is missing a playable Spotify reference.');
        return;
      }
      if (!ensureAuthenticated() || !token) {
        return;
      }
      const provider = overrides?.provider ?? state?.provider ?? activeProvider ?? DEFAULT_PROVIDER;
      setActiveProvider(provider);
      try {
        await runAction(() => startPlayback(token, { provider, track_uri: uri }), { silent: false });
      } catch {
        // handled globally
      }
    },
    [activeProvider, ensureAuthenticated, runAction, state?.provider, token],
  );

  const pause = useCallback(async () => {
    if (!ensureAuthenticated() || !token) {
      return;
    }
    const provider = state?.provider ?? activeProvider;
    const deviceId = state?.device?.id ?? undefined;
    try {
      await runAction(() => pausePlayback(token, { provider, device_id: deviceId }), { silent: false });
    } catch {
      // handled globally
    }
  }, [activeProvider, ensureAuthenticated, runAction, state?.device?.id, state?.provider, token]);

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
    } catch {
      // handled globally
    }
  }, [activeProvider, ensureAuthenticated, runAction, state?.device?.id, state?.provider, token]);

  const next = useCallback(async () => {
    if (!ensureAuthenticated() || !token) {
      return;
    }
    const provider = state?.provider ?? activeProvider;
    const deviceId = state?.device?.id ?? undefined;
    try {
      await runAction(() => nextTrack(token, { provider, device_id: deviceId }), { silent: false });
    } catch {
      // handled globally
    }
  }, [activeProvider, ensureAuthenticated, runAction, state?.device?.id, state?.provider, token]);

  const previous = useCallback(async () => {
    if (!ensureAuthenticated() || !token) {
      return;
    }
    const provider = state?.provider ?? activeProvider;
    const deviceId = state?.device?.id ?? undefined;
    try {
      await runAction(() => previousTrack(token, { provider, device_id: deviceId }), { silent: false });
    } catch {
      // handled globally
    }
  }, [activeProvider, ensureAuthenticated, runAction, state?.device?.id, state?.provider, token]);

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
    if (!state?.is_playing || !token) {
      return undefined;
    }
    const interval = window.setInterval(() => {
      void refresh();
    }, 10000);
    return () => window.clearInterval(interval);
  }, [refresh, state?.is_playing, token]);

  const value = useMemo<PlaybackContextValue>(
    () => ({
      state,
      error,
      isBusy,
      isPlaying,
      canControl,
      activeTrackUri,
      playTrack,
      pause,
      resume,
      next,
      previous,
      refresh,
    }),
    [activeTrackUri, canControl, error, isBusy, isPlaying, next, pause, playTrack, previous, refresh, resume, state],
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
