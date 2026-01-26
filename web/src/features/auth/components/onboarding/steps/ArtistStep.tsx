/**
 * ArtistStep
 *
 * Select your "ride or die" artist with search autocomplete.
 */

import { useState, useEffect, useRef } from 'react';
import { useOnboarding } from '../context/OnboardingProvider';
import { searchArtists } from '../api/onboardingApi';
import { STEP_CONFIG } from '../types';
import type { Artist } from '../types';

type Props = {
  token: string;
};

export default function ArtistStep({ token }: Props) {
  const { state, dispatch, goNext, currentStepIndex, totalSteps } = useOnboarding();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Artist[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const selectedArtist = state.data.rideOrDieArtist;
  const config = STEP_CONFIG.artist;

  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    if (!query.trim()) {
      setResults([]);
      setShowResults(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setIsSearching(true);
      try {
        const data = await searchArtists(query, token);
        setResults(data);
        setShowResults(true);
      } catch {
        setResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 300);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [query, token]);

  const selectArtist = (artist: Artist) => {
    dispatch({ type: 'SET_RIDE_OR_DIE_ARTIST', artist });
    setQuery('');
    setShowResults(false);
  };

  const clearArtist = () => {
    dispatch({ type: 'SET_RIDE_OR_DIE_ARTIST', artist: null });
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
        {selectedArtist ? (
          <div className="onboarding__selected-artist">
            <div className="onboarding__selected-artist-img">
              {selectedArtist.imageUrl && <img src={selectedArtist.imageUrl} alt={selectedArtist.name} />}
            </div>
            <div className="onboarding__selected-artist-info">
              <div className="onboarding__selected-artist-name">{selectedArtist.name}</div>
              <div className="onboarding__selected-artist-label">Your ride-or-die</div>
            </div>
            <button
              className="onboarding__selected-artist-remove"
              onClick={clearArtist}
              type="button"
              aria-label="Remove artist"
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
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
            <input
              type="text"
              className="onboarding__search-input"
              placeholder="Search for an artist..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => results.length > 0 && setShowResults(true)}
            />
            {showResults && (
              <div className="onboarding__search-results">
                {isSearching ? (
                  <div className="onboarding__search-loading">Searching...</div>
                ) : results.length > 0 ? (
                  results.map((artist) => (
                    <button
                      key={artist.id}
                      className="onboarding__search-result"
                      onClick={() => selectArtist(artist)}
                      type="button"
                    >
                      <div className="onboarding__search-result-img">
                        {artist.imageUrl && <img src={artist.imageUrl} alt={artist.name} />}
                      </div>
                      <span className="onboarding__search-result-name">{artist.name}</span>
                    </button>
                  ))
                ) : query.trim() ? (
                  <div className="onboarding__search-loading">No artists found</div>
                ) : null}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="onboarding__footer">
        <div className="onboarding__btn-row">
          <button className="onboarding__btn onboarding__btn--secondary" onClick={goNext} type="button">
            Skip for now
          </button>
          <button className="onboarding__btn onboarding__btn--primary" onClick={goNext} type="button">
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
