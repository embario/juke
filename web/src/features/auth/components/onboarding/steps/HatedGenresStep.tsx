/**
 * HatedGenresStep
 *
 * Select genres you can't stand (excludes your favorite genres).
 */

import { useState, useEffect } from 'react';
import { useOnboarding } from '../context/OnboardingProvider';
import { fetchFeaturedGenres } from '../api/onboardingApi';
import { STEP_CONFIG } from '../types';
import type { Genre } from '../types';

type Props = {
  token: string;
};

export default function HatedGenresStep({ token }: Props) {
  const { state, dispatch, goNext, currentStepIndex, totalSteps } = useOnboarding();
  const [genres, setGenres] = useState<Genre[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const selectedHated = state.data.hatedGenres;
  const favoriteGenres = state.data.favoriteGenres;
  const config = STEP_CONFIG.hated;

  useEffect(() => {
    async function loadGenres() {
      setIsLoading(true);
      try {
        const data = await fetchFeaturedGenres();
        // Filter out favorite genres
        const available = data.filter((g) => !favoriteGenres.includes(g.id));
        setGenres(available);
      } catch (err) {
        console.error('Failed to load genres:', err);
      } finally {
        setIsLoading(false);
      }
    }
    loadGenres();
  }, [token, favoriteGenres]);

  const toggleGenre = (genreId: string) => {
    const current = selectedHated;
    if (current.includes(genreId)) {
      dispatch({ type: 'SET_HATED_GENRES', genres: current.filter((id) => id !== genreId) });
    } else if (current.length < 3) {
      dispatch({ type: 'SET_HATED_GENRES', genres: [...current, genreId] });
    }
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
        {isLoading ? (
          <div className="onboarding__selection-count">Loading...</div>
        ) : (
          <>
            <div className="onboarding__genre-grid">
              {genres.map((genre) => {
                const isSelected = selectedHated.includes(genre.id);
                const isDisabled = selectedHated.length >= 3 && !isSelected;

                return (
                  <button
                    key={genre.id}
                    className={`onboarding__genre-card ${isSelected ? 'onboarding__genre-card--selected' : ''}`}
                    onClick={() => toggleGenre(genre.id)}
                    disabled={isDisabled}
                    type="button"
                  >
                    <span className="onboarding__genre-name">{genre.name}</span>
                    <span className="onboarding__genre-artist-names">
                      {genre.topArtists.map((a) => a.name).join(', ')}
                    </span>
                    {isSelected && (
                      <div className="onboarding__genre-check">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
            <div className="onboarding__selection-count">
              {selectedHated.length}/3 selected (optional)
            </div>
          </>
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
