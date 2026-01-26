/**
 * ConnectStep
 *
 * Final step - shows summary and Spotify connection.
 * Saves profile data and redirects to Juke World.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../../hooks/useAuth';
import { useOnboarding } from '../context/OnboardingProvider';
import { saveOnboardingProfile, getSpotifyOAuthUrl } from '../api/onboardingApi';

type Props = {
  token: string;
};

export default function ConnectStep({ token }: Props) {
  const navigate = useNavigate();
  const { username } = useAuth();
  const { state, dispatch, clearDraft, currentStepIndex, totalSteps } = useOnboarding();
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const data = state.data;

  const handleSaveAndConnect = async (connectSpotify: boolean) => {
    setIsSaving(true);
    setError(null);

    try {
      // Save profile data
      await saveOnboardingProfile(data, token);

      // Mark as complete and clear draft
      dispatch({ type: 'MARK_COMPLETE' });
      clearDraft();

      if (connectSpotify) {
        // Redirect to Spotify OAuth
        window.location.href = getSpotifyOAuthUrl();
      } else {
        // Navigate to Juke World with welcome state
        const focusState = data.location
          ? {
              welcomeUser: true,
              focusLat: data.location.lat,
              focusLng: data.location.lng,
              focusUsername: username ?? undefined,
            }
          : { welcomeUser: true };
        navigate('/world', { state: focusState });
      }
    } catch {
      setError('Failed to save your profile. Please try again.');
      setIsSaving(false);
    }
  };

  // Summary stats
  const genreCount = data.favoriteGenres.length;
  const hasArtist = !!data.rideOrDieArtist;
  const hasLocation = !!data.location;
  const decade = data.favoriteDecade;
  const style = data.listeningStyle;

  return (
    <div className="onboarding__card onboarding__complete">
      <div className="onboarding__header">
        <span className="onboarding__step-label">
          Step {currentStepIndex + 1} of {totalSteps}
        </span>

        <div className="onboarding__complete-icon">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        </div>

        <h1 className="onboarding__title">Your music identity is ready!</h1>
        <p className="onboarding__subtitle">
          Connect Spotify to complete your profile and see yourself on Juke World
        </p>
      </div>

      <div className="onboarding__content">
        <div className="onboarding__summary">
          <div className="onboarding__summary-item">
            <span className="onboarding__summary-label">Genres</span>
            <span className="onboarding__summary-value">{genreCount} selected</span>
          </div>
          {hasArtist && (
            <div className="onboarding__summary-item">
              <span className="onboarding__summary-label">Ride-or-Die</span>
              <span className="onboarding__summary-value">{data.rideOrDieArtist?.name}</span>
            </div>
          )}
          {decade && (
            <div className="onboarding__summary-item">
              <span className="onboarding__summary-label">Era</span>
              <span className="onboarding__summary-value">{decade}</span>
            </div>
          )}
          {style && (
            <div className="onboarding__summary-item">
              <span className="onboarding__summary-label">Style</span>
              <span className="onboarding__summary-value">
                {style === 'playlist' ? 'Playlist' : 'Album'}
              </span>
            </div>
          )}
          {hasLocation && (
            <div className="onboarding__summary-item">
              <span className="onboarding__summary-label">Location</span>
              <span className="onboarding__summary-value">{data.location?.name}</span>
            </div>
          )}
        </div>

        {error && (
          <div style={{ color: 'var(--clr-error)', textAlign: 'center', marginBottom: '16px' }}>
            {error}
          </div>
        )}
      </div>

      <div className="onboarding__footer">
        <button
          className="onboarding__btn onboarding__btn--spotify"
          onClick={() => handleSaveAndConnect(true)}
          disabled={isSaving}
          type="button"
        >
          {isSaving ? (
            'Saving...'
          ) : (
            <>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z" />
              </svg>
              Connect Spotify & Enter Juke World
            </>
          )}
        </button>

        <button
          className="onboarding__btn onboarding__btn--secondary"
          onClick={() => handleSaveAndConnect(false)}
          disabled={isSaving}
          type="button"
        >
          Skip Spotify for now
        </button>
      </div>
    </div>
  );
}
