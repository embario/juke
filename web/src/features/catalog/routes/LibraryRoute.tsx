import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type {
  Album,
  AlbumDetail,
  Artist,
  ArtistDetail,
  CatalogResourceType,
  CatalogResults,
  GenreDetail,
  NavigationStackItem,
  SearchHistoryResourcePayload,
  Track,
} from '../types';
import { useAuth } from '../../auth/hooks/useAuth';
import StatusBanner from '@uikit/components/StatusBanner';
import { createSearchHistory } from '../api/searchHistoryApi';
import {
  fetchAlbumDetail,
  fetchAlbumDetailBySpotifyId,
  fetchAllCatalogResources,
  fetchArtistDetail,
  fetchArtistDetailBySpotifyId,
  fetchGenreDetail,
} from '../api/catalogApi';
import { usePlayback } from '../../playback/hooks/usePlayback';
import { deriveTrackUri } from '../../playback/utils';
import { buildSpotifyConnectPath } from '../../auth/constants';
import { formatDuration } from '@shared/utils/formatters';

type DetailType = 'genre' | 'artist' | 'album';
type DetailCache = Record<string, GenreDetail | ArtistDetail | AlbumDetail>;

type SearchSession = {
  query: string;
  resultKeys: Set<string>;
  engaged: SearchHistoryResourcePayload[];
};

type SpotifyResolveResult = {
  id: number;
  name: string;
};

const EMPTY_RESULTS: CatalogResults = {
  genres: [],
  artists: [],
  albums: [],
  tracks: [],
};

const buildResourceKey = (resourceType: CatalogResourceType, resourceId: number) => `${resourceType}:${resourceId}`;

const parseNumericId = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }

    if (/^\d+$/.test(trimmed)) {
      return Number(trimmed);
    }

    const match = trimmed.match(/\/(\d+)\/?$/);
    if (match) {
      return Number(match[1]);
    }
  }

  if (value && typeof value === 'object' && 'id' in value) {
    return parseNumericId((value as { id?: unknown }).id);
  }

  return null;
};

const resolveResourceId = (resource: { id?: unknown; pk?: unknown; url?: unknown }): number | null => {
  return parseNumericId(resource.id) ?? parseNumericId(resource.pk) ?? parseNumericId(resource.url);
};

const artworkFromImages = (value: unknown): string | null => {
  if (!Array.isArray(value)) {
    return null;
  }

  const first = value.find((entry) => typeof entry === 'string' && entry.trim().length > 0);
  return typeof first === 'string' ? first : null;
};

const getArtworkUrl = (resource: { spotify_data?: Record<string, unknown>; custom_data?: Record<string, unknown> }): string | null => {
  const imageFromSpotify = artworkFromImages(resource.spotify_data?.images);
  if (imageFromSpotify) {
    return imageFromSpotify;
  }

  const custom = resource.custom_data?.image_url;
  return typeof custom === 'string' && custom.trim() ? custom : null;
};

const buildResultKeySet = (results: CatalogResults): Set<string> => {
  const keys = new Set<string>();

  results.genres.forEach((genre) => {
    const id = resolveResourceId(genre);
    if (id !== null) {
      keys.add(buildResourceKey('genre', id));
    }
  });

  results.artists.forEach((artist) => {
    const id = resolveResourceId(artist);
    if (id !== null) {
      keys.add(buildResourceKey('artist', id));
    }
  });

  results.albums.forEach((album) => {
    const id = resolveResourceId(album);
    if (id !== null) {
      keys.add(buildResourceKey('album', id));
    }
  });

  results.tracks.forEach((track) => {
    const id = resolveResourceId(track);
    if (id !== null) {
      keys.add(buildResourceKey('track', id));
    }
  });

  return keys;
};

const artistNames = (album: Album): string => {
  if (!Array.isArray(album.artists) || album.artists.length === 0) {
    return 'Unknown artist';
  }

  const names = album.artists
    .map((entry) => {
      if (typeof entry === 'string') {
        const id = parseNumericId(entry);
        return id === null ? entry : `Artist ${id}`;
      }
      if (typeof entry === 'number') {
        return `Artist ${entry}`;
      }
      return entry.name;
    })
    .filter(Boolean);

  return names.length ? names.join(', ') : 'Unknown artist';
};

const genreNames = (artist: Artist): string => {
  const namesFromGenres = Array.isArray(artist.genres)
    ? artist.genres
      .map((entry) => {
        if (typeof entry === 'string') {
          return entry.includes('/genres/') ? null : entry;
        }
        if (typeof entry === 'number') {
          return null;
        }
        return entry.name;
      })
      .filter((value): value is string => Boolean(value))
    : [];

  if (namesFromGenres.length > 0) {
    return namesFromGenres.join(', ');
  }

  const spotifyGenres = artist.spotify_data?.genres;
  if (Array.isArray(spotifyGenres) && spotifyGenres.length > 0) {
    const labels = spotifyGenres.filter((value): value is string => typeof value === 'string' && value.trim().length > 0);
    if (labels.length > 0) {
      return labels.join(', ');
    }
  }

  return 'Genres';
};

const spotifyContextUri = (resourceType: 'artist' | 'album', spotifyId: string | undefined): string | null => {
  if (!spotifyId) {
    return null;
  }
  if (spotifyId.startsWith('spotify:')) {
    return spotifyId;
  }
  return `spotify:${resourceType}:${spotifyId}`;
};

const formatReleaseYear = (releaseDate: string | undefined): string => {
  if (!releaseDate || typeof releaseDate !== 'string') {
    return 'Unknown year';
  }
  const [year] = releaseDate.split('-');
  return year || 'Unknown year';
};

const formatRuntime = (durationMs: number): string => {
  if (!Number.isFinite(durationMs) || durationMs <= 0) {
    return 'Unknown runtime';
  }
  const totalMinutes = Math.round(durationMs / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) {
    return `${minutes}m`;
  }
  return `${hours}h ${minutes}m`;
};

const resolveArtistHeroArtwork = (artist: ArtistDetail): string | null => {
  const directArtwork = getArtworkUrl(artist);
  if (directArtwork) {
    return directArtwork;
  }

  const albumArtwork = artist.albums.map((album) => getArtworkUrl(album)).find((value) => typeof value === 'string' && value.length > 0);
  return albumArtwork ?? null;
};

const resolveAlbumHeroArtwork = (album: AlbumDetail): string | null => {
  const directArtwork = getArtworkUrl(album);
  if (directArtwork) {
    return directArtwork;
  }

  const trackArtwork = album.tracks
    .map((track) => artworkFromImages(track.spotify_data?.images))
    .find((value) => typeof value === 'string' && value.length > 0);
  return trackArtwork ?? null;
};

const CatalogLoadingIndicator = ({ label }: { label: string }) => (
  <div className="catalog-loading" role="status" aria-live="polite" aria-label={label}>
    <div className="catalog-loading__halo" />
    <div className="catalog-loading__bars" aria-hidden="true">
      <span />
      <span />
      <span />
      <span />
      <span />
    </div>
    <p className="catalog-loading__label">{label}</p>
  </div>
);

const LibraryRoute = () => {
  const { isAuthenticated, token } = useAuth();
  const { playTrack, playContext, canControl, activeTrackUri, isPlaying, error: playbackError } = usePlayback();

  const [searchParams, setSearchParams] = useSearchParams();
  const queryParam = searchParams.get('q') ?? '';
  const [fieldValue, setFieldValue] = useState(queryParam);
  const [results, setResults] = useState<CatalogResults>(EMPTY_RESULTS);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [navigationStack, setNavigationStack] = useState<NavigationStackItem[]>([]);
  const [detailCache, setDetailCache] = useState<DetailCache>({});
  const [activeDetailKey, setActiveDetailKey] = useState<string | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const lastAppliedQueryRef = useRef('');
  const lastHandledOpenRef = useRef<string | null>(null);
  const searchSessionRef = useRef<SearchSession | null>(null);

  const syncActiveDetailFromStack = useCallback((nextStack: NavigationStackItem[]) => {
    const tail = nextStack[nextStack.length - 1];
    if (!tail || tail.resourceType === 'search' || tail.resourceId === undefined) {
      setActiveDetailKey(null);
      return;
    }
    setActiveDetailKey(buildResourceKey(tail.resourceType, tail.resourceId));
  }, []);

  const flushSearchSession = useCallback(async () => {
    const current = searchSessionRef.current;
    if (!current) {
      return;
    }

    searchSessionRef.current = null;
    if (!token || current.engaged.length === 0) {
      return;
    }

    try {
      await createSearchHistory(token, {
        search_query: current.query,
        engaged_resources: current.engaged,
      });
    } catch {
      // Best-effort analytics write.
    }
  }, [token]);

  const runSearch = useCallback(
    async (query: string) => {
      const trimmed = query.trim();

      if (!token) {
        setError('Authenticate to browse the catalog.');
        setResults(EMPTY_RESULTS);
        return;
      }

      if (!trimmed) {
        await flushSearchSession();
        setResults(EMPTY_RESULTS);
        setNavigationStack([]);
        setActiveDetailKey(null);
        setDetailError(null);
        setError(null);
        return;
      }

      const currentSession = searchSessionRef.current;
      if (currentSession && currentSession.query !== trimmed) {
        await flushSearchSession();
      }

      setIsLoading(true);
      setError(null);
      setDetailError(null);

      try {
        const payload = await fetchAllCatalogResources(token, trimmed);
        const searchRoot: NavigationStackItem = {
          resourceType: 'search',
          label: `Search: "${trimmed}"`,
          searchQuery: trimmed,
        };

        setResults(payload);
        setNavigationStack([searchRoot]);
        setActiveDetailKey(null);
        searchSessionRef.current = {
          query: trimmed,
          resultKeys: buildResultKeySet(payload),
          engaged: [],
        };
      } catch (searchError) {
        setError(searchError instanceof Error ? searchError.message : 'Unable to fetch catalog.');
        setResults(EMPTY_RESULTS);
      } finally {
        setIsLoading(false);
      }
    },
    [flushSearchSession, token],
  );

  const fetchDetail = useCallback(
    async (resourceType: DetailType, resourceId: number) => {
      if (!token) {
        throw new Error('Authenticate to browse the catalog.');
      }
      if (resourceType === 'genre') {
        return fetchGenreDetail(token, resourceId);
      }
      if (resourceType === 'artist') {
        return fetchArtistDetail(token, resourceId);
      }
      return fetchAlbumDetail(token, resourceId);
    },
    [token],
  );

  const maybeTrackSearchEngagement = useCallback(
    async (resourceType: CatalogResourceType, resourceId: number, resourceName: string) => {
      const session = searchSessionRef.current;
      if (!session) {
        return;
      }

      const key = buildResourceKey(resourceType, resourceId);
      if (!session.resultKeys.has(key)) {
        await flushSearchSession();
        return;
      }

      const exists = session.engaged.some(
        (entry) => entry.resource_type === resourceType && entry.resource_id === resourceId,
      );

      if (!exists) {
        session.engaged.push({
          resource_type: resourceType,
          resource_id: resourceId,
          resource_name: resourceName,
        });
      }
    },
    [flushSearchSession],
  );

  const resolveArtistNavigationId = useCallback(
    async (artist: Artist) => {
      const directId = resolveResourceId(artist);
      if (directId !== null) {
        return {
          id: directId,
          name: artist.name,
        } satisfies SpotifyResolveResult;
      }

      if (!token || !artist.spotify_id) {
        return null;
      }

      try {
        const hydrated = await fetchArtistDetailBySpotifyId(token, artist.spotify_id);
        const resolvedId = resolveResourceId(hydrated);
        if (resolvedId === null) {
          return null;
        }
        setDetailCache((prev) => ({
          ...prev,
          [buildResourceKey('artist', resolvedId)]: hydrated,
        }));
        return {
          id: resolvedId,
          name: hydrated.name,
        } satisfies SpotifyResolveResult;
      } catch {
        return null;
      }
    },
    [token],
  );

  const resolveArtistBySpotifyId = useCallback(
    async (spotifyId: string) => {
      if (!token || !spotifyId) {
        return null;
      }
      try {
        const hydrated = await fetchArtistDetailBySpotifyId(token, spotifyId);
        const resolvedId = resolveResourceId(hydrated);
        if (resolvedId === null) {
          return null;
        }
        setDetailCache((prev) => ({
          ...prev,
          [buildResourceKey('artist', resolvedId)]: hydrated,
        }));
        return {
          id: resolvedId,
          name: hydrated.name,
        } satisfies SpotifyResolveResult;
      } catch {
        return null;
      }
    },
    [token],
  );

  const resolveAlbumBySpotifyId = useCallback(
    async (spotifyId: string) => {
      if (!token || !spotifyId) {
        return null;
      }
      try {
        const hydrated = await fetchAlbumDetailBySpotifyId(token, spotifyId);
        const resolvedId = resolveResourceId(hydrated);
        if (resolvedId === null) {
          return null;
        }
        setDetailCache((prev) => ({
          ...prev,
          [buildResourceKey('album', resolvedId)]: hydrated,
        }));
        return {
          id: resolvedId,
          name: hydrated.name,
        } satisfies SpotifyResolveResult;
      } catch {
        return null;
      }
    },
    [token],
  );

  const openDetailResource = useCallback(
    async (resourceType: DetailType, resourceId: number, resourceName: string, source: 'search' | 'detail') => {
      if (isDetailLoading) {
        return;
      }

      await maybeTrackSearchEngagement(resourceType, resourceId, resourceName);

      const resourceKey = buildResourceKey(resourceType, resourceId);
      const cached = detailCache[resourceKey];
      const cachedAlbumIsPartial =
        resourceType === 'album'
        && Boolean(cached)
        && Array.isArray((cached as AlbumDetail).tracks)
        && ((cached as AlbumDetail).tracks?.length ?? 0) < ((cached as AlbumDetail).total_tracks ?? 0);
      const shouldFetch = !cached || cachedAlbumIsPartial;

      setDetailError(null);
      setNavigationStack((prev) => {
        const node: NavigationStackItem = {
          resourceType,
          resourceId,
          label: resourceName,
        };

        if (source === 'search') {
          const searchRoot = prev.find((entry) => entry.resourceType === 'search');
          const next = searchRoot ? [searchRoot, node] : [node];
          syncActiveDetailFromStack(next);
          return next;
        }

        const existingIndex = prev.findIndex(
          (entry) => entry.resourceType === resourceType && entry.resourceId === resourceId,
        );
        const next = existingIndex >= 0 ? prev.slice(0, existingIndex + 1) : [...prev, node];
        syncActiveDetailFromStack(next);
        return next;
      });

      if (!shouldFetch) {
        return;
      }

      try {
        setIsDetailLoading(true);
        const detail = await fetchDetail(resourceType, resourceId);
        setDetailCache((prev) => ({
          ...prev,
          [resourceKey]: detail as GenreDetail | ArtistDetail | AlbumDetail,
        }));
      } catch (detailFetchError) {
        setDetailError(detailFetchError instanceof Error ? detailFetchError.message : 'Unable to load detail view.');
      } finally {
        setIsDetailLoading(false);
      }
    },
    [detailCache, fetchDetail, isDetailLoading, maybeTrackSearchEngagement, syncActiveDetailFromStack],
  );

  useEffect(() => {
    setFieldValue((prev) => (prev === queryParam ? prev : queryParam));

    if (queryParam.trim() && queryParam !== lastAppliedQueryRef.current) {
      lastAppliedQueryRef.current = queryParam;
      void runSearch(queryParam);
    }

    if (!queryParam) {
      lastAppliedQueryRef.current = '';
    }
  }, [queryParam, runSearch]);

  useEffect(() => {
    const resourceType = searchParams.get('open');
    const spotifyId = searchParams.get('sid');

    if (!resourceType || !spotifyId) {
      lastHandledOpenRef.current = null;
      return;
    }

    if (!token) {
      return;
    }

    if (resourceType !== 'artist' && resourceType !== 'album') {
      return;
    }

    const deepLinkKey = `${resourceType}:${spotifyId}`;
    if (lastHandledOpenRef.current === deepLinkKey) {
      return;
    }
    lastHandledOpenRef.current = deepLinkKey;

    const hydrateAndOpen = async () => {
      const resolved = resourceType === 'artist'
        ? await resolveArtistBySpotifyId(spotifyId)
        : await resolveAlbumBySpotifyId(spotifyId);

      if (!resolved) {
        setDetailError('Unable to open this resource from playback right now.');
      } else {
        await openDetailResource(resourceType, resolved.id, resolved.name, 'detail');
      }

      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete('open');
      nextParams.delete('sid');
      setSearchParams(nextParams, { replace: true });
    };

    void hydrateAndOpen();
  }, [openDetailResource, resolveAlbumBySpotifyId, resolveArtistBySpotifyId, searchParams, setSearchParams, token]);

  const handleSubmit = (value: string) => {
    const trimmed = value.trim();
    const next = new URLSearchParams(searchParams);

    if (trimmed) {
      next.set('q', trimmed);
    } else {
      next.delete('q');
      void flushSearchSession();
      setResults(EMPTY_RESULTS);
      setNavigationStack([]);
      setActiveDetailKey(null);
      setDetailError(null);
    }

    setSearchParams(next, { replace: true });
  };

  const handleBreadcrumbClick = (index: number) => {
    setNavigationStack((prev) => {
      const next = prev.slice(0, index + 1);
      syncActiveDetailFromStack(next);
      return next;
    });
  };

  const handleReset = async () => {
    await flushSearchSession();
    setSearchParams(new URLSearchParams(), { replace: true });
    setFieldValue('');
    setResults(EMPTY_RESULTS);
    setNavigationStack([]);
    setActiveDetailKey(null);
    setDetailError(null);
    setError(null);
    lastAppliedQueryRef.current = '';
  };

  const handleTrackPlay = async (track: Track, contextUri?: string | null) => {
    const trackId = resolveResourceId(track);
    if (trackId !== null) {
      await maybeTrackSearchEngagement('track', trackId, track.name);
    }

    if (!canStartPlayback) {
      return;
    }

    void playTrack(track, contextUri ? { contextUri } : undefined);
  };

  const activeDetail = useMemo(() => {
    if (!activeDetailKey) {
      return null;
    }
    return detailCache[activeDetailKey] ?? null;
  }, [activeDetailKey, detailCache]);

  const selectedNode = navigationStack[navigationStack.length - 1];
  const searchMatchCount =
    results.genres.length + results.artists.length + results.albums.length + results.tracks.length;
  const requiresSpotifyLink = Boolean(playbackError && /link .*spotify|link a streaming account/i.test(playbackError));
  const canStartPlayback = canControl && !requiresSpotifyLink;
  const isDetailView = Boolean(selectedNode && selectedNode.resourceType !== 'search');
  const hasSearchQuery = Boolean(queryParam.trim());
  const spotifyConnectPath = buildSpotifyConnectPath(
    token,
    typeof window !== 'undefined' ? window.location.href : undefined,
  );

  return (
    <section className="library library--story">
      <div className="catalog-shell">
        <div className="catalog-shell__body">
          <div className="catalog-search-island">
            <form
              className="search search--catalog"
              onSubmit={(event) => {
                event.preventDefault();
                handleSubmit(fieldValue);
              }}
            >
              <div className="search__field">
                <input
                  placeholder="Search genres, artists, albums, tracks..."
                  value={fieldValue}
                  onChange={(event) => setFieldValue(event.target.value)}
                />
                <button type="submit" className="btn btn-primary">
                  Search
                </button>
              </div>
            </form>
          </div>

          {!isAuthenticated ? (
            <StatusBanner
              variant="warning"
              message={
                <>
                  Authentication required. <Link to="/login">Sign in</Link> or <Link to="/register">create an account</Link>.
                </>
              }
            />
          ) : null}

          {navigationStack.length > 0 ? (
            <div className="catalog-nav">
              <div className="catalog-nav__crumbs">
                <button type="button" className="btn btn-link" onClick={() => void handleReset()}>
                  Home
                </button>
                {navigationStack.map((item, index) => (
                  index === navigationStack.length - 1 ? (
                    <span
                      key={`${item.resourceType}-${item.resourceId ?? index}`}
                      className="catalog-nav__crumb catalog-nav__crumb--active"
                      aria-current="page"
                    >
                      {item.label}
                    </span>
                  ) : (
                    <button
                      type="button"
                      key={`${item.resourceType}-${item.resourceId ?? index}`}
                      className="btn btn-link"
                      onClick={() => handleBreadcrumbClick(index)}
                    >
                      {item.label}
                    </button>
                  )
                ))}
              </div>
            </div>
          ) : null}

          <StatusBanner variant="error" message={error} />
          <StatusBanner variant="error" message={detailError} />
          {requiresSpotifyLink ? (
            <StatusBanner
              variant="warning"
              message={
                <>
                  Playback unavailable: Spotify is not linked for this account yet. <a href={spotifyConnectPath}>Connect Spotify</a> (also available as a small link near the bottom of the sidebar), then retry play.
                </>
              }
            />
          ) : null}
          {!requiresSpotifyLink ? <StatusBanner variant="warning" message={playbackError} /> : null}

          {isDetailView || hasSearchQuery ? (
          <div className={`catalog-content${isDetailView ? ' catalog-content--detail' : ''}`}>
            {!isDetailView && hasSearchQuery ? (
              <section className="catalog-results">
                <div className="catalog-results__header">
                  <p className="eyebrow">Search Results</p>
                  <h3>{queryParam ? `${searchMatchCount} matches` : 'Run a search to begin'}</h3>
                </div>

                {isLoading ? <CatalogLoadingIndicator label="Loading fresh music results..." /> : null}
                {!isLoading && queryParam && searchMatchCount === 0 ? <p className="muted">No matches found.</p> : null}

              {results.genres.length > 0 ? (
                <div className="catalog-section">
                  <h4>Genres</h4>
                  <div className="catalog-grid">
                    {results.genres.map((genre) => {
                      const genreId = resolveResourceId(genre);
                      return (
                        <button
                          key={`genre-${genre.spotify_id}-${genre.id}`}
                          type="button"
                          className="catalog-card"
                          disabled={genreId === null}
                          onClick={() => {
                            if (genreId === null) {
                              return;
                            }
                            void openDetailResource('genre', genreId, genre.name, 'search');
                          }}
                        >
                          <div className="catalog-card__media catalog-card__media--genre" aria-hidden="true">
                            <span>♪</span>
                          </div>
                          <span className="eyebrow">Genre</span>
                          <h5>{genre.name}</h5>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              {results.artists.length > 0 ? (
                <div className="catalog-section">
                  <h4>Artists</h4>
                  <div className="catalog-grid">
                    {results.artists.map((artist) => {
                      const artistId = resolveResourceId(artist);
                      const canOpenArtist = artistId !== null || Boolean(artist.spotify_id);
                      const artworkUrl = getArtworkUrl(artist);
                      return (
                        <button
                          key={`artist-${artist.spotify_id}-${artist.id}`}
                          type="button"
                          className="catalog-card"
                          disabled={!canOpenArtist}
                          onClick={async () => {
                            const resolvedArtist = await resolveArtistNavigationId(artist);
                            if (!resolvedArtist) {
                              setDetailError('Unable to load this artist right now. Please try another result.');
                              return;
                            }
                            void openDetailResource('artist', resolvedArtist.id, resolvedArtist.name, 'search');
                          }}
                        >
                          <div className="catalog-card__media" aria-hidden={!artworkUrl}>
                            {artworkUrl ? <img src={artworkUrl} alt={`${artist.name} artwork`} loading="lazy" /> : <span>{artist.name.charAt(0) || '♪'}</span>}
                          </div>
                          <span className="eyebrow">Artist</span>
                          <h5>{artist.name}</h5>
                          <p className="muted">{genreNames(artist)}</p>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              {results.albums.length > 0 ? (
                <div className="catalog-section">
                  <h4>Albums</h4>
                  <div className="catalog-grid">
                    {results.albums.map((album) => {
                      const albumId = resolveResourceId(album);
                      const artworkUrl = getArtworkUrl(album);
                      return (
                        <button
                          key={`album-${album.spotify_id}-${album.id}`}
                          type="button"
                          className="catalog-card"
                          disabled={albumId === null}
                          onClick={() => {
                            if (albumId === null) {
                              return;
                            }
                            void openDetailResource('album', albumId, album.name, 'search');
                          }}
                        >
                          <div className="catalog-card__media" aria-hidden={!artworkUrl}>
                            {artworkUrl ? <img src={artworkUrl} alt={`${album.name} artwork`} loading="lazy" /> : <span>{album.name.charAt(0) || '♪'}</span>}
                          </div>
                          <span className="eyebrow">Album</span>
                          <h5>{album.name}</h5>
                          <p className="muted">
                            {artistNames(album)} • {album.total_tracks} tracks
                          </p>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              {results.tracks.length > 0 ? (
                <div className="catalog-section">
                  <h4>Tracks</h4>
                  <ul className="catalog-track-list catalog-track-list--table">
                    <li className="catalog-track-item catalog-track-item--header" aria-hidden="true">
                      <div className="catalog-track-main">
                        <span className="catalog-track-index">#</span>
                        <span>Track</span>
                      </div>
                      <div className="catalog-track-meta">
                        <span>Duration</span>
                      </div>
                    </li>
                    {results.tracks.map((track) => {
                      const trackUri = deriveTrackUri(track);
                      const isActiveTrack = Boolean(trackUri && activeTrackUri && trackUri === activeTrackUri);
                      const interactiveClass = canStartPlayback ? ' catalog-track-item--interactive' : '';
                      const activeClass = isActiveTrack ? ' catalog-track-item--active' : '';

                      return (
                        <li
                          key={`track-${track.spotify_id}-${track.id}`}
                          className={`catalog-track-item${interactiveClass}${activeClass}`}
                          onDoubleClick={() => void handleTrackPlay(track)}
                          title={canStartPlayback ? 'Double-click to play' : 'Connect Spotify to play'}
                        >
                          <div className="catalog-track-main">
                            <span className="catalog-track-index">{track.track_number || '—'}</span>
                            <div className="catalog-track-main__text">
                              <strong>{track.name}</strong>
                            </div>
                          </div>
                          <div className="catalog-track-meta">
                            <span className="muted">{formatDuration(track.duration_ms)}</span>
                            {isActiveTrack && isPlaying ? <span className="catalog-track-state">Playing</span> : null}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ) : null}
              </section>
            ) : null}

            {isDetailView ? (
            <section className="catalog-detail catalog-detail--full">
              <div className="catalog-detail__body">
                {isDetailLoading ? <CatalogLoadingIndicator label="Loading detailed music story..." /> : null}

                {!isDetailLoading && activeDetail && selectedNode?.resourceType === 'genre' ? (
                  <div className="detail-view">
                    <p className="eyebrow">Genre Detail</p>
                    <h3>{activeDetail.name}</h3>
                    <p>{(activeDetail as GenreDetail).description ?? 'No description available yet.'}</p>
                    <h4>Top Artists</h4>
                    <ul className="catalog-detail-list">
                      {((activeDetail as GenreDetail).top_artists ?? []).map((artist, index) => {
                        const artistId = resolveResourceId(artist);
                        const canOpenArtist = artistId !== null || Boolean(artist.spotify_id);
                        const artworkUrl = getArtworkUrl(artist);

                        return (
                          <li key={`genre-artist-${artist.spotify_id}-${artist.id}`} className="catalog-detail-list__row">
                            <span>{index + 1}</span>
                            <div className="catalog-detail-list__art" aria-hidden={!artworkUrl}>
                              {artworkUrl ? <img src={artworkUrl} alt={`${artist.name} artwork`} loading="lazy" /> : <span>{artist.name.charAt(0) || '♪'}</span>}
                            </div>
                            <div>
                              <strong>{artist.name}</strong>
                              <p className="muted">{genreNames(artist)}</p>
                            </div>
                            <button
                              type="button"
                              className="btn btn-link"
                              disabled={!canOpenArtist}
                              onClick={async () => {
                                const resolvedArtist = await resolveArtistNavigationId(artist);
                                if (!resolvedArtist) {
                                  setDetailError('Unable to load this artist right now. Please try another result.');
                                  return;
                                }
                                void openDetailResource('artist', resolvedArtist.id, resolvedArtist.name, 'detail');
                              }}
                            >
                              View
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ) : null}

                {!isDetailLoading && activeDetail && selectedNode?.resourceType === 'artist' ? (
                  (() => {
                    const artistDetail = activeDetail as ArtistDetail;
                    const heroArtwork = resolveArtistHeroArtwork(artistDetail);
                    const popularity = typeof artistDetail.spotify_data?.popularity === 'number'
                      ? artistDetail.spotify_data.popularity
                      : null;

                    return (
                      <div className="detail-view">
                        <div className="catalog-hero">
                          <div className="catalog-hero__art" aria-hidden={!heroArtwork}>
                            {heroArtwork ? (
                              <img src={heroArtwork} alt={`${artistDetail.name} artwork`} loading="lazy" />
                            ) : (
                              <span>{artistDetail.name.charAt(0) || '♪'}</span>
                            )}
                          </div>
                          <div className="catalog-hero__body">
                            <p className="eyebrow">Artist</p>
                            <h3>{artistDetail.name}</h3>
                            <p className="catalog-hero__lede">{artistDetail.bio ?? 'No biography available yet.'}</p>
                            <div className="catalog-hero__facts">
                              <span className="pill">Genres: {artistDetail.genres.length}</span>
                              <span className="pill">Albums: {artistDetail.albums.length}</span>
                              <span className="pill">Top Tracks: {Math.min(artistDetail.top_tracks.length, 5)}</span>
                              {popularity !== null ? <span className="pill">Popularity: {popularity}</span> : null}
                            </div>
                          </div>
                        </div>

                        <div className="detail-actions">
                          <button
                            type="button"
                            className="btn btn-primary"
                            disabled={!canStartPlayback}
                            onClick={() => {
                              const contextUri = spotifyContextUri('artist', artistDetail.spotify_id);
                              if (!contextUri) {
                                return;
                              }
                              void playContext(contextUri);
                            }}
                          >
                            Play Top 5 Hits
                          </button>
                        </div>

                        <h4>Genres</h4>
                        <div className="catalog-chip-row">
                          {(artistDetail.genres ?? []).map((genre) => {
                            const genreId = resolveResourceId(genre);

                            return (
                              <button
                                key={`artist-genre-${genre.spotify_id}-${genre.id}`}
                                type="button"
                                className="chip chip--active"
                                disabled={genreId === null}
                                onClick={() => {
                                  if (genreId === null) {
                                    return;
                                  }
                                  void openDetailResource('genre', genreId, genre.name, 'detail');
                                }}
                              >
                                {genre.name}
                              </button>
                            );
                          })}
                        </div>

                        <h4>Discography</h4>
                        <div className="catalog-grid">
                          {(artistDetail.albums ?? []).map((album) => {
                            const albumId = resolveResourceId(album);
                            const artworkUrl = getArtworkUrl(album);

                            return (
                              <button
                                key={`artist-album-${album.spotify_id}-${album.id}`}
                                type="button"
                                className="catalog-card"
                                disabled={albumId === null}
                                onClick={() => {
                                  if (albumId === null) {
                                    return;
                                  }
                                  void openDetailResource('album', albumId, album.name, 'detail');
                                }}
                              >
                                <div className="catalog-card__media" aria-hidden={!artworkUrl}>
                                  {artworkUrl ? <img src={artworkUrl} alt={`${album.name} artwork`} loading="lazy" /> : <span>{album.name.charAt(0) || '♪'}</span>}
                                </div>
                                <span className="eyebrow">Album</span>
                                <h5>{album.name}</h5>
                                <p className="muted">{album.total_tracks} tracks</p>
                              </button>
                            );
                          })}
                        </div>

                        <h4>Top Tracks</h4>
                        <ul className="catalog-track-list catalog-track-list--table">
                          <li className="catalog-track-item catalog-track-item--header" aria-hidden="true">
                            <div className="catalog-track-main">
                              <span className="catalog-track-index">#</span>
                              <span>Track</span>
                            </div>
                            <div className="catalog-track-meta">
                              <span>Duration</span>
                            </div>
                          </li>
                          {(artistDetail.top_tracks ?? []).slice(0, 5).map((track, index) => {
                            const trackUri = deriveTrackUri(track);
                            const isActiveTrack = Boolean(trackUri && activeTrackUri && trackUri === activeTrackUri);
                            const interactiveClass = canStartPlayback ? ' catalog-track-item--interactive' : '';
                            const activeClass = isActiveTrack ? ' catalog-track-item--active' : '';

                            return (
                              <li
                                key={`artist-track-${track.spotify_id}-${track.id}`}
                                className={`catalog-track-item${interactiveClass}${activeClass}`}
                                onDoubleClick={() => void handleTrackPlay(track)}
                                title={canStartPlayback ? 'Double-click to play' : 'Connect Spotify to play'}
                              >
                                <div className="catalog-track-main">
                                  <span className="catalog-track-index">{track.track_number || index + 1}</span>
                                  <div className="catalog-track-main__text">
                                    <strong>{track.name}</strong>
                                  </div>
                                </div>
                                <div className="catalog-track-meta">
                                  <span className="muted">{formatDuration(track.duration_ms)}</span>
                                  {isActiveTrack && isPlaying ? <span className="catalog-track-state">Playing</span> : null}
                                </div>
                              </li>
                            );
                          })}
                        </ul>

                        <h4>Related Artists</h4>
                        <div className="catalog-grid">
                          {(artistDetail.related_artists ?? []).map((artist) => {
                            const artistId = resolveResourceId(artist);
                            const canOpenArtist = artistId !== null || Boolean(artist.spotify_id);
                            const artworkUrl = getArtworkUrl(artist);

                            return (
                              <button
                                key={`related-artist-${artist.spotify_id}-${artist.id}`}
                                type="button"
                                className="catalog-card"
                                disabled={!canOpenArtist}
                                onClick={async () => {
                                  const resolvedArtist = await resolveArtistNavigationId(artist);
                                  if (!resolvedArtist) {
                                    setDetailError('Unable to load this artist right now. Please try another result.');
                                    return;
                                  }
                                  void openDetailResource('artist', resolvedArtist.id, resolvedArtist.name, 'detail');
                                }}
                              >
                                <div className="catalog-card__media" aria-hidden={!artworkUrl}>
                                  {artworkUrl ? <img src={artworkUrl} alt={`${artist.name} artwork`} loading="lazy" /> : <span>{artist.name.charAt(0) || '♪'}</span>}
                                </div>
                                <span className="eyebrow">Artist</span>
                                <h5>{artist.name}</h5>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })()
                ) : null}

                {!isDetailLoading && activeDetail && selectedNode?.resourceType === 'album' ? (
                  (() => {
                    const albumDetail = activeDetail as AlbumDetail;
                    const heroArtwork = resolveAlbumHeroArtwork(albumDetail);
                    const totalDurationMs = (albumDetail.tracks ?? []).reduce((sum, track) => sum + (track.duration_ms || 0), 0);
                    const albumArtists = artistNames(albumDetail);
                    const albumContextUri = spotifyContextUri('album', albumDetail.spotify_id);

                    return (
                      <div className="detail-view">
                        <div className="catalog-hero">
                          <div className="catalog-hero__art" aria-hidden={!heroArtwork}>
                            {heroArtwork ? (
                              <img src={heroArtwork} alt={`${albumDetail.name} artwork`} loading="lazy" />
                            ) : (
                              <span>{albumDetail.name.charAt(0) || '♪'}</span>
                            )}
                          </div>
                          <div className="catalog-hero__body">
                            <p className="eyebrow">Album</p>
                            <h3>{albumDetail.name}</h3>
                            <p className="catalog-hero__lede">{albumDetail.description ?? 'No album notes available yet.'}</p>
                            <div className="catalog-hero__facts">
                              <span className="pill">Year: {formatReleaseYear(albumDetail.release_date)}</span>
                              <span className="pill">Duration: {formatRuntime(totalDurationMs)}</span>
                              <span className="pill">Songs: {albumDetail.total_tracks}</span>
                              <span className="pill">Loaded: {albumDetail.tracks.length}</span>
                            </div>
                            <p className="catalog-hero__supporting">{albumArtists}</p>
                          </div>
                        </div>

                        <div className="detail-actions">
                          <button
                            type="button"
                            className="btn btn-primary"
                            disabled={!canStartPlayback}
                            onClick={() => {
                              if (!albumContextUri) {
                                return;
                              }
                              void playContext(albumContextUri);
                            }}
                          >
                            Play Album
                          </button>
                        </div>

                        <h4>Tracks</h4>
                        <ul className="catalog-track-list catalog-track-list--table">
                          <li className="catalog-track-item catalog-track-item--header" aria-hidden="true">
                            <div className="catalog-track-main">
                              <span className="catalog-track-index">#</span>
                              <span>Track</span>
                            </div>
                            <div className="catalog-track-meta">
                              <span>Duration</span>
                            </div>
                          </li>
                          {(albumDetail.tracks ?? []).map((track) => {
                            const trackUri = deriveTrackUri(track);
                            const isActiveTrack = Boolean(trackUri && activeTrackUri && trackUri === activeTrackUri);
                            const interactiveClass = canStartPlayback ? ' catalog-track-item--interactive' : '';
                            const activeClass = isActiveTrack ? ' catalog-track-item--active' : '';

                            return (
                              <li
                                key={`album-track-${track.spotify_id}-${track.id}`}
                                className={`catalog-track-item${interactiveClass}${activeClass}`}
                                onDoubleClick={() => void handleTrackPlay(track, albumContextUri)}
                                title={canStartPlayback ? 'Double-click to play' : 'Connect Spotify to play'}
                              >
                                <div className="catalog-track-main">
                                  <span className="catalog-track-index">{track.track_number || '—'}</span>
                                  <div className="catalog-track-main__text">
                                    <strong>{track.name}</strong>
                                  </div>
                                </div>
                                <div className="catalog-track-meta">
                                  <span className="muted">{formatDuration(track.duration_ms)}</span>
                                  {isActiveTrack && isPlaying ? <span className="catalog-track-state">Playing</span> : null}
                                </div>
                              </li>
                            );
                          })}
                        </ul>

                        <h4>Related Albums</h4>
                        <div className="catalog-grid">
                          {(albumDetail.related_albums ?? []).map((album) => {
                            const albumId = resolveResourceId(album);
                            const artworkUrl = getArtworkUrl(album);

                            return (
                              <button
                                key={`related-album-${album.spotify_id}-${album.id}`}
                                type="button"
                                className="catalog-card"
                                disabled={albumId === null}
                                onClick={() => {
                                  if (albumId === null) {
                                    return;
                                  }
                                  void openDetailResource('album', albumId, album.name, 'detail');
                                }}
                              >
                                <div className="catalog-card__media" aria-hidden={!artworkUrl}>
                                  {artworkUrl ? <img src={artworkUrl} alt={`${album.name} artwork`} loading="lazy" /> : <span>{album.name.charAt(0) || '♪'}</span>}
                                </div>
                                <span className="eyebrow">Album</span>
                                <h5>{album.name}</h5>
                                <p className="muted">{album.total_tracks} tracks</p>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })()
                ) : null}
              </div>
            </section>
            ) : null}
          </div>
          ) : null}
        </div>
      </div>
    </section>
  );
};

export default LibraryRoute;
