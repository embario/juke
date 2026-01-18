import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Button from '@uikit/components/Button';
import { useAuth } from '../../auth/hooks/useAuth';
import { fetchAllCatalogResources } from '../../catalog/api/catalogApi';
import type { CatalogResults } from '../../catalog/types';

const createEmptyResults = (): CatalogResults => ({
  genres: [],
  artists: [],
  albums: [],
  tracks: [],
});

const MIN_QUERY_LENGTH = 2;

const SidebarSearch = () => {
  const navigate = useNavigate();
  const { token, isAuthenticated } = useAuth();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<CatalogResults>(() => createEmptyResults());
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (!isAuthenticated || !token) {
      setResults(createEmptyResults());
      setIsLoading(false);
      setError(null);
      return;
    }

    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setResults(createEmptyResults());
      setIsLoading(false);
      setError(null);
      return;
    }

    setIsLoading(true);
    setError(null);

    const handle = window.setTimeout(async () => {
      requestIdRef.current += 1;
      const currentId = requestIdRef.current;
      try {
        const payload = await fetchAllCatalogResources(token, trimmed);
        if (currentId !== requestIdRef.current) {
          return;
        }
        setResults(payload);
      } catch (fetchError) {
        if (currentId !== requestIdRef.current) {
          return;
        }
        setError(fetchError instanceof Error ? fetchError.message : 'Unable to search catalog.');
        setResults(createEmptyResults());
      } finally {
        if (currentId === requestIdRef.current) {
          setIsLoading(false);
        }
      }
    }, 250);

    return () => window.clearTimeout(handle);
  }, [isAuthenticated, query, token]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      return;
    }
    navigate({ pathname: '/', search: `?q=${encodeURIComponent(trimmed)}` });
  };

  const handleQuickNavigate = (value: string) => {
    if (!value) {
      return;
    }
    setQuery(value);
    navigate({ pathname: '/', search: `?q=${encodeURIComponent(value)}` });
  };

  const sections = useMemo(
    () => [
      {
        key: 'artists',
        title: 'Artists',
        items: results.artists.slice(0, 3).map((artist) => ({
          id: artist.spotify_id ?? `${artist.id ?? artist.name}-artist`,
          title: artist.name,
          subtitle: Array.isArray(artist.genres) && artist.genres.length
            ? artist.genres
                .map((genre) => (typeof genre === 'string' ? genre : genre.name))
                .filter(Boolean)
                .slice(0, 2)
                .join(', ')
            : 'No genres tagged',
        })),
      },
      {
        key: 'albums',
        title: 'Albums',
        items: results.albums.slice(0, 3).map((album) => ({
          id: album.spotify_id ?? `${album.id ?? album.name}-album`,
          title: album.name,
          subtitle: Array.isArray(album.artists) && album.artists.length
            ? `by ${album.artists
                .map((entry) =>
                  typeof entry === 'string'
                    ? entry
                    : typeof entry === 'number'
                      ? `Artist ${entry}`
                      : entry.name,
                )
                .filter(Boolean)
                .slice(0, 2)
                .join(', ')}`
            : 'Unknown artist',
        })),
      },
      {
        key: 'tracks',
        title: 'Tracks',
        items: results.tracks.slice(0, 3).map((track) => ({
          id: track.spotify_id ?? `${track.id ?? track.name}-track`,
          title: track.name,
          subtitle: typeof track.album === 'object' && track.album
            ? track.album.name
            : typeof track.album === 'string'
              ? track.album
              : 'Single',
        })),
      },
    ],
    [results],
  );

  const hasResults = sections.some((section) => section.items.length > 0);

  return (
    <div className="sidebar-search">
      <form className="sidebar-search__form" onSubmit={handleSubmit}>
        <label>
          <span>Quick query</span>
          <input
            className="sidebar-search__input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={isAuthenticated ? 'Search artists, albums, tracks' : 'Sign in to search the catalog'}
            disabled={!isAuthenticated}
            aria-label="Sidebar catalog search"
          />
        </label>
        <Button type="submit" variant="ghost" disabled={!query.trim() || !isAuthenticated}>
          Send query
        </Button>
      </form>
      {isAuthenticated ? (
        <p className="sidebar-search__status">
          {isLoading && 'Scanning catalog…'}
          {!isLoading && error}
          {!isLoading && !error && !hasResults && query.trim().length >= MIN_QUERY_LENGTH && 'No matches yet.'}
        </p>
      ) : (
        <p className="sidebar-search__status">Authentication required to preview catalog results.</p>
      )}
      {hasResults && (
        <div className="sidebar-search__results">
          {sections.map((section) =>
            section.items.length ? (
              <div key={section.key} className="sidebar-search__section">
                <h4>{section.title}</h4>
                {section.items.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    className="sidebar-search__item"
                    onClick={() => handleQuickNavigate(item.title)}
                  >
                    <div>
                      <p>{item.title}</p>
                      <span>{item.subtitle}</span>
                    </div>
                    <span className="sidebar-search__badge">{section.title}</span>
                  </button>
                ))}
              </div>
            ) : null,
          )}
        </div>
      )}
    </div>
  );
};

export default SidebarSearch;
