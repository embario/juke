import { FormEvent, useEffect, useState } from 'react';
import clsx from 'clsx';
import Button from '@uikit/components/Button';
import type { CatalogFilter } from '../types';

type Props = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  filters: CatalogFilter[];
  onToggleFilter: (filter: CatalogFilter) => void;
};

const FILTER_OPTIONS: CatalogFilter[] = ['albums', 'artists', 'tracks'];

const SearchBar = ({ value, onChange, onSubmit, filters, onToggleFilter }: Props) => {
  const [localValue, setLocalValue] = useState(value);

  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(localValue);
  };

  return (
    <form className="search" onSubmit={handleSubmit}>
      <div className="search__field">
        <input
          placeholder="Scan the catalog…"
          value={localValue}
          onChange={(event) => {
            setLocalValue(event.target.value);
            onChange(event.target.value);
          }}
        />
        <Button type="submit" className="search__button">
          Query
        </Button>
      </div>
      <div className="search__filters" role="group" aria-label="Result filters">
        {FILTER_OPTIONS.map((filter) => (
          <button
            type="button"
            key={filter}
            className={clsx('chip', filters.includes(filter) && 'chip--active')}
            onClick={() => onToggleFilter(filter)}
          >
            {filter}
          </button>
        ))}
      </div>
    </form>
  );
};

export default SearchBar;
