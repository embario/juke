/**
 * GenreStep
 *
 * First step of onboarding - select top 3 genres.
 * Displays genres with top artist thumbnails from Spotify.
 */

import { useState, useEffect } from 'react';
import { useOnboarding } from '../context/OnboardingProvider';
import { fetchFeaturedGenres } from '../api/onboardingApi';
import { STEP_CONFIG } from '../types';
import type { Genre } from '../types';

type Props = {
  token: string;
};

export default function GenreStep({ token }: Props) {
  const { state, dispatch, goNext, currentStepIndex, totalSteps } = useOnboarding();
  const [genres, setGenres] = useState<Genre[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const selectedGenres = state.data.favoriteGenres;
  const config = STEP_CONFIG.genres;

  useEffect(() => {
    async function loadGenres() {
      setIsLoading(true);
      try {
        const data = await fetchFeaturedGenres();
        setGenres(data);
      } catch (err) {
        console.error('Failed to load genres:', err);
      } finally {
        setIsLoading(false);
      }
    }
    loadGenres();
  }, [token]);

  const toggleGenre = (genreId: string) => {
    const current = selectedGenres;
    if (current.includes(genreId)) {
      dispatch({ type: 'SET_FAVORITE_GENRES', genres: current.filter((id) => id !== genreId) });
    } else if (current.length < 3) {
      dispatch({ type: 'SET_FAVORITE_GENRES', genres: [...current, genreId] });
    }
  };

  const canContinue = selectedGenres.length > 0;

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
          <div className="onboarding__selection-count">Loading genres...</div>
        ) : (
          <>
            <div className="onboarding__genre-grid">
              {genres.map((genre) => {
                const isSelected = selectedGenres.includes(genre.id);
                const isDisabled = selectedGenres.length >= 3 && !isSelected;

                return (
                  <button
                    key={genre.id}
                    className={`onboarding__genre-card ${isSelected ? 'onboarding__genre-card--selected' : ''}`}
                    onClick={() => toggleGenre(genre.id)}
                    disabled={isDisabled}
                    type="button"
                  >
                    <div className="onboarding__genre-artists">
                      {genre.topArtists.slice(0, 3).map((artist, i) => (
                        <div key={i} className="onboarding__genre-artist-img">
                          {artist.imageUrl && <img src={artist.imageUrl} alt={artist.name} />}
                        </div>
                      ))}
                    </div>
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
            <div className="onboarding__selection-count">{selectedGenres.length}/3 selected</div>
          </>
        )}
      </div>

      <div className="onboarding__footer">
        <button
          className="onboarding__btn onboarding__btn--primary"
          onClick={goNext}
          disabled={!canContinue}
          type="button"
        >
          Continue
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    </div>
  );
}
