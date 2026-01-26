/**
 * Preference Steps
 *
 * Decade, Listening Style, and Age Range selection steps.
 */

import { useOnboarding } from '../context/OnboardingProvider';
import { STEP_CONFIG, DECADES, AGE_RANGES } from '../types';
import type { Decade, ListeningStyle, AgeRange } from '../types';

// Decade Step
export function DecadeStep() {
  const { state, dispatch, goNext, currentStepIndex, totalSteps } = useOnboarding();
  const selected = state.data.favoriteDecade;
  const config = STEP_CONFIG.decade;

  const selectDecade = (decade: Decade) => {
    dispatch({ type: 'SET_FAVORITE_DECADE', decade });
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
        <div className="onboarding__decade-grid">
          {DECADES.map((decade) => (
            <button
              key={decade.id}
              className={`onboarding__decade-btn ${selected === decade.id ? 'onboarding__decade-btn--selected' : ''}`}
              onClick={() => selectDecade(decade.id)}
              type="button"
            >
              <span className="onboarding__decade-label">{decade.label}</span>
              <span className="onboarding__decade-vibe">{decade.vibe}</span>
            </button>
          ))}
        </div>
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

// Listening Style Step
export function ListeningStyleStep() {
  const { state, dispatch, goNext, currentStepIndex, totalSteps } = useOnboarding();
  const selected = state.data.listeningStyle;
  const config = STEP_CONFIG.listening;

  const selectStyle = (style: ListeningStyle) => {
    dispatch({ type: 'SET_LISTENING_STYLE', style });
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
        <div className="onboarding__binary-grid">
          <button
            className={`onboarding__binary-card ${selected === 'playlist' ? 'onboarding__binary-card--selected' : ''}`}
            onClick={() => selectStyle('playlist')}
            type="button"
          >
            <span className="onboarding__binary-icon">🔀</span>
            <span className="onboarding__binary-label">Playlist Person</span>
            <span className="onboarding__binary-desc">Curated vibes, shuffle on, discover new tracks</span>
          </button>

          <button
            className={`onboarding__binary-card ${selected === 'album' ? 'onboarding__binary-card--selected' : ''}`}
            onClick={() => selectStyle('album')}
            type="button"
          >
            <span className="onboarding__binary-icon">💿</span>
            <span className="onboarding__binary-label">Album Listener</span>
            <span className="onboarding__binary-desc">Front to back, the way it was meant to be heard</span>
          </button>
        </div>
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

// Age Range Step
export function AgeRangeStep() {
  const { state, dispatch, goNext, currentStepIndex, totalSteps } = useOnboarding();
  const selected = state.data.ageRange;
  const config = STEP_CONFIG.age;

  const selectAge = (range: AgeRange) => {
    dispatch({ type: 'SET_AGE_RANGE', range });
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
        <div className="onboarding__pill-row">
          {AGE_RANGES.map((range) => (
            <button
              key={range}
              className={`onboarding__pill ${selected === range ? 'onboarding__pill--selected' : ''}`}
              onClick={() => selectAge(range)}
              type="button"
            >
              {range}
            </button>
          ))}
        </div>
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
