/**
 * LocationStep
 *
 * City search for Juke World map placement.
 */

import { useState, useEffect, useRef } from 'react';
import { useOnboarding } from '../context/OnboardingProvider';
import { searchCities } from '../api/onboardingApi';
import { STEP_CONFIG } from '../types';
import type { CityLocation } from '../types';

export default function LocationStep() {
  const { state, dispatch, goNext, currentStepIndex, totalSteps } = useOnboarding();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<CityLocation[]>([]);
  const [showResults, setShowResults] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const selected = state.data.location;
  const config = STEP_CONFIG.location;

  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    if (!query.trim()) {
      return;
    }

    debounceRef.current = setTimeout(async () => {
      const data = await searchCities(query);
      setResults(data);
      setShowResults(true);
    }, 200);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [query]);

  const selectCity = (city: CityLocation) => {
    dispatch({ type: 'SET_LOCATION', location: city });
    setQuery('');
    setShowResults(false);
  };

  const clearLocation = () => {
    dispatch({ type: 'SET_LOCATION', location: null });
  };

  return (
    <div className="onboarding__card">
      <div className="onboarding__header">
        <span className="onboarding__step-label">
          Step {currentStepIndex + 1} of {totalSteps}
        </span>
        <h1 className="onboarding__title">{config.title}</h1>
        <p className="onboarding__subtitle">{config.subtitle}</p>
      </div>

      <div className="onboarding__content">
        {selected ? (
          <div className="onboarding__location-selected">
            <div className="onboarding__location-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
                <circle cx="12" cy="10" r="3" />
              </svg>
            </div>
            <div className="onboarding__location-info">
              <div className="onboarding__location-name">{selected.name}</div>
              <div className="onboarding__location-country">{selected.country}</div>
            </div>
            <button
              className="onboarding__location-remove"
              onClick={clearLocation}
              type="button"
              aria-label="Remove location"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        ) : (
          <div className="onboarding__search">
            <svg className="onboarding__search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
              <circle cx="12" cy="10" r="3" />
            </svg>
            <input
              type="text"
              className="onboarding__search-input"
              placeholder="Search for your city..."
              value={query}
              onChange={(e) => {
                const nextQuery = e.target.value;
                setQuery(nextQuery);
                if (!nextQuery.trim()) {
                  setResults([]);
                  setShowResults(false);
                }
              }}
              onFocus={() => results.length > 0 && setShowResults(true)}
            />
            {showResults && results.length > 0 && (
              <div className="onboarding__search-results">
                {results.map((city, i) => (
                  <button
                    key={`${city.name}-${city.country}-${i}`}
                    className="onboarding__search-result"
                    onClick={() => selectCity(city)}
                    type="button"
                  >
                    <div className="onboarding__search-result-img">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
                        <circle cx="12" cy="10" r="3" />
                      </svg>
                    </div>
                    <span className="onboarding__search-result-name">
                      {city.name}, {city.country}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="onboarding__footer">
        <div className="onboarding__btn-row">
          <button className="onboarding__btn onboarding__btn--secondary" onClick={goNext} type="button">
            Skip
          </button>
          <button className="onboarding__btn onboarding__btn--primary" onClick={goNext} type="button">
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
