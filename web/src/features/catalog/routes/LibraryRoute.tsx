import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import SearchBar from '../components/SearchBar';
import ResultsPanel from '../components/ResultsPanel';
import { useCatalogSearch } from '../hooks/useCatalogSearch';
import type { CatalogFilter } from '../types';
import { useAuth } from '../../auth/hooks/useAuth';
import StatusBanner from '@uikit/components/StatusBanner';

const DEFAULT_FILTERS: CatalogFilter[] = ['albums', 'artists', 'tracks'];

const LibraryRoute = () => {
  const { isAuthenticated } = useAuth();
  const [filters, setFilters] = useState<CatalogFilter[]>(DEFAULT_FILTERS);
  const [searchParams, setSearchParams] = useSearchParams();
  const queryParam = searchParams.get('q') ?? '';
  const [fieldValue, setFieldValue] = useState(queryParam);
  const lastAppliedQueryRef = useRef('');
  const { data, runSearch, isLoading, error } = useCatalogSearch();

  useEffect(() => {
    // Sync the search field when the query param changes via navigation.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFieldValue((prev) => (prev === queryParam ? prev : queryParam));
    if (queryParam && queryParam !== lastAppliedQueryRef.current) {
      lastAppliedQueryRef.current = queryParam;
      runSearch(queryParam);
    }
    if (!queryParam) {
      lastAppliedQueryRef.current = '';
    }
  }, [queryParam, runSearch]);

  const toggleFilter = (filter: CatalogFilter) => {
    setFilters((prev) => {
      if (prev.includes(filter)) {
        if (prev.length === 1) {
          return prev;
        }
        return prev.filter((entry) => entry !== filter);
      }
      return [...prev, filter];
    });
  };

  const handleSubmit = (value: string) => {
    const trimmed = value.trim();
    const next = new URLSearchParams(searchParams);
    if (trimmed) {
      next.set('q', trimmed);
    } else {
      next.delete('q');
    }
    setSearchParams(next, { replace: true });
  };

  return (
    <section className="library">
      <div className="library__hero">
        <p className="eyebrow">Exploration</p>
        <h2>Interrogate the catalog in real time</h2>
        <p className="muted">Query albums, artists, and tracks pulled from the Django API.</p>
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
      </div>
      <SearchBar
        value={fieldValue}
        onChange={setFieldValue}
        onSubmit={handleSubmit}
        filters={filters}
        onToggleFilter={toggleFilter}
      />
      <ResultsPanel data={data} filters={filters} isLoading={isLoading} error={error} />
    </section>
  );
};

export default LibraryRoute;
