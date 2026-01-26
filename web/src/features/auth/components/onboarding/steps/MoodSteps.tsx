/**
 * Mood Steps
 *
 * Rainy Day and Workout vibe selection steps.
 */

import { useOnboarding } from '../context/OnboardingProvider';
import { STEP_CONFIG, RAINY_DAY_MOODS, WORKOUT_VIBES } from '../types';

// Rainy Day Step
export function RainyDayStep() {
  const { state, dispatch, goNext, currentStepIndex, totalSteps } = useOnboarding();
  const selected = state.data.rainyDayMood;
  const config = STEP_CONFIG.rainy;

  const selectMood = (moodId: string) => {
    dispatch({ type: 'SET_RAINY_DAY_MOOD', mood: moodId });
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
        <div className="onboarding__mood-grid">
          {RAINY_DAY_MOODS.map((mood) => (
            <button
              key={mood.id}
              className={`onboarding__mood-card ${selected === mood.id ? 'onboarding__mood-card--selected' : ''}`}
              onClick={() => selectMood(mood.id)}
              type="button"
            >
              <span className="onboarding__mood-icon">{mood.icon}</span>
              <span className="onboarding__mood-label">{mood.label}</span>
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

// Workout Step
export function WorkoutStep() {
  const { state, dispatch, goNext, currentStepIndex, totalSteps } = useOnboarding();
  const selected = state.data.workoutVibe;
  const config = STEP_CONFIG.workout;

  const selectVibe = (vibeId: string) => {
    dispatch({ type: 'SET_WORKOUT_VIBE', vibe: vibeId });
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
        <div className="onboarding__workout-grid">
          {WORKOUT_VIBES.map((vibe) => (
            <button
              key={vibe.id}
              className={`onboarding__workout-card ${selected === vibe.id ? 'onboarding__workout-card--selected' : ''}`}
              onClick={() => selectVibe(vibe.id)}
              type="button"
            >
              <span className="onboarding__workout-icon">{vibe.icon}</span>
              <span className="onboarding__workout-label">{vibe.label}</span>
              <span className="onboarding__workout-desc">{vibe.description}</span>
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
