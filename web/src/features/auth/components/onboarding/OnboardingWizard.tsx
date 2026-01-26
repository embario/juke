/**
 * OnboardingWizard
 *
 * Main wizard component that orchestrates all onboarding steps.
 * Uses Card Stack design - one question per screen with smooth transitions.
 */

import { useOnboarding, OnboardingProvider } from './context/OnboardingProvider';

import GenreStep from './steps/GenreStep';
import ArtistStep from './steps/ArtistStep';
import HatedGenresStep from './steps/HatedGenresStep';
import { RainyDayStep, WorkoutStep } from './steps/MoodSteps';
import { DecadeStep, ListeningStyleStep, AgeRangeStep } from './steps/PreferenceSteps';
import LocationStep from './steps/LocationStep';
import ConnectStep from './steps/ConnectStep';

import './onboarding.css';

function WizardContent() {
  const { state, goBack, canGoBack, progress, clearDraft, dispatch } = useOnboarding();
  const token = localStorage.getItem('juke-auth-state')
    ? JSON.parse(localStorage.getItem('juke-auth-state') || '{}').token
    : '';

  const currentStep = state.currentStep;

  const handleRestart = () => {
    if (window.confirm('Are you sure you want to restart? All your answers will be cleared.')) {
      clearDraft();
      dispatch({ type: 'RESET' });
    }
  };

  return (
    <div className="onboarding">
      {/* Progress Bar */}
      <div className="onboarding__progress">
        <div className="onboarding__progress-fill" style={{ width: `${progress}%` }} />
      </div>

      {/* Back Button */}
      {canGoBack && currentStep !== 'connect' && (
        <button className="onboarding__back" onClick={goBack} type="button" aria-label="Go back">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
        </button>
      )}

      {/* Restart Button */}
      <button
        className="onboarding__restart"
        onClick={handleRestart}
        type="button"
        aria-label="Restart onboarding"
        title="Start over"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
          <path d="M3 3v5h5" />
        </svg>
      </button>

      {/* Main Content */}
      <main className="onboarding__main">
        {currentStep === 'genres' && <GenreStep token={token} />}
        {currentStep === 'artist' && <ArtistStep token={token} />}
        {currentStep === 'hated' && <HatedGenresStep token={token} />}
        {currentStep === 'rainy' && <RainyDayStep />}
        {currentStep === 'workout' && <WorkoutStep />}
        {currentStep === 'decade' && <DecadeStep />}
        {currentStep === 'listening' && <ListeningStyleStep />}
        {currentStep === 'age' && <AgeRangeStep />}
        {currentStep === 'location' && <LocationStep />}
        {currentStep === 'connect' && <ConnectStep token={token} />}
      </main>
    </div>
  );
}

export default function OnboardingWizard() {
  return (
    <OnboardingProvider>
      <WizardContent />
    </OnboardingProvider>
  );
}
