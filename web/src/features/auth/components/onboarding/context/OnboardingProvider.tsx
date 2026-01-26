/**
 * OnboardingProvider
 *
 * Context provider for onboarding wizard state with localStorage persistence.
 * Allows users to resume onboarding if they leave and come back.
 */

import { createContext, useContext, useReducer, useEffect, useCallback, ReactNode } from 'react';
import {
  OnboardingState,
  OnboardingAction,
  OnboardingData,
  OnboardingStep,
  ONBOARDING_STEPS,
} from '../types';

const STORAGE_KEY = 'juke-onboarding-draft';
const DRAFT_EXPIRY_DAYS = 30;

// Initial state
const initialData: OnboardingData = {
  favoriteGenres: [],
  rideOrDieArtist: null,
  hatedGenres: [],
  rainyDayMood: null,
  workoutVibe: null,
  favoriteDecade: null,
  listeningStyle: null,
  ageRange: null,
  location: null,
  spotifyConnected: false,
};

const initialState: OnboardingState = {
  currentStep: 'genres',
  data: initialData,
  isSubmitting: false,
  error: null,
  completedAt: null,
};

// Reducer
function onboardingReducer(state: OnboardingState, action: OnboardingAction): OnboardingState {
  switch (action.type) {
    case 'SET_STEP':
      return { ...state, currentStep: action.step, error: null };

    case 'SET_FAVORITE_GENRES':
      return { ...state, data: { ...state.data, favoriteGenres: action.genres } };

    case 'SET_RIDE_OR_DIE_ARTIST':
      return { ...state, data: { ...state.data, rideOrDieArtist: action.artist } };

    case 'SET_HATED_GENRES':
      return { ...state, data: { ...state.data, hatedGenres: action.genres } };

    case 'SET_RAINY_DAY_MOOD':
      return { ...state, data: { ...state.data, rainyDayMood: action.mood } };

    case 'SET_WORKOUT_VIBE':
      return { ...state, data: { ...state.data, workoutVibe: action.vibe } };

    case 'SET_FAVORITE_DECADE':
      return { ...state, data: { ...state.data, favoriteDecade: action.decade } };

    case 'SET_LISTENING_STYLE':
      return { ...state, data: { ...state.data, listeningStyle: action.style } };

    case 'SET_AGE_RANGE':
      return { ...state, data: { ...state.data, ageRange: action.range } };

    case 'SET_LOCATION':
      return { ...state, data: { ...state.data, location: action.location } };

    case 'SET_SPOTIFY_CONNECTED':
      return { ...state, data: { ...state.data, spotifyConnected: action.connected } };

    case 'SET_SUBMITTING':
      return { ...state, isSubmitting: action.isSubmitting };

    case 'SET_ERROR':
      return { ...state, error: action.error, isSubmitting: false };

    case 'MARK_COMPLETE':
      return { ...state, completedAt: new Date().toISOString() };

    case 'RESET':
      return initialState;

    default:
      return state;
  }
}

// Context
type OnboardingContextValue = {
  state: OnboardingState;
  dispatch: React.Dispatch<OnboardingAction>;

  // Navigation helpers
  goToStep: (step: OnboardingStep) => void;
  goNext: () => void;
  goBack: () => void;
  currentStepIndex: number;
  totalSteps: number;
  progress: number;
  canGoBack: boolean;
  canGoNext: boolean;

  // Data helpers
  updateGenres: (genres: string[]) => void;
  toggleGenre: (genreId: string) => void;

  // Persistence helpers
  clearDraft: () => void;
  hasDraft: () => boolean;
};

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

// Load state from localStorage
function loadDraft(): OnboardingState | null {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return null;

    const parsed = JSON.parse(saved) as OnboardingState & { savedAt?: string };

    // Check if draft is expired
    if (parsed.savedAt) {
      const savedDate = new Date(parsed.savedAt);
      const expiryDate = new Date(savedDate.getTime() + DRAFT_EXPIRY_DAYS * 24 * 60 * 60 * 1000);
      if (new Date() > expiryDate) {
        localStorage.removeItem(STORAGE_KEY);
        return null;
      }
    }

    // Don't restore if already completed
    if (parsed.completedAt) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }

    return parsed;
  } catch {
    return null;
  }
}

// Save state to localStorage
function saveDraft(state: OnboardingState) {
  try {
    const toSave = { ...state, savedAt: new Date().toISOString() };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
  } catch {
    // Silently fail if localStorage is unavailable
  }
}

// Provider component
export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(onboardingReducer, initialState, () => {
    const draft = loadDraft();
    return draft || initialState;
  });

  // Auto-save to localStorage on state changes
  useEffect(() => {
    if (!state.completedAt) {
      saveDraft(state);
    }
  }, [state]);

  // Navigation helpers
  const currentStepIndex = ONBOARDING_STEPS.indexOf(state.currentStep);
  const totalSteps = ONBOARDING_STEPS.length;
  const progress = ((currentStepIndex + 1) / totalSteps) * 100;
  const canGoBack = currentStepIndex > 0;
  const canGoNext = currentStepIndex < totalSteps - 1;

  const goToStep = useCallback((step: OnboardingStep) => {
    dispatch({ type: 'SET_STEP', step });
  }, []);

  const goNext = useCallback(() => {
    if (canGoNext) {
      dispatch({ type: 'SET_STEP', step: ONBOARDING_STEPS[currentStepIndex + 1] });
    }
  }, [canGoNext, currentStepIndex]);

  const goBack = useCallback(() => {
    if (canGoBack) {
      dispatch({ type: 'SET_STEP', step: ONBOARDING_STEPS[currentStepIndex - 1] });
    }
  }, [canGoBack, currentStepIndex]);

  // Data helpers
  const updateGenres = useCallback((genres: string[]) => {
    dispatch({ type: 'SET_FAVORITE_GENRES', genres });
  }, []);

  const toggleGenre = useCallback((genreId: string) => {
    const current = state.data.favoriteGenres;
    if (current.includes(genreId)) {
      dispatch({ type: 'SET_FAVORITE_GENRES', genres: current.filter((id) => id !== genreId) });
    } else if (current.length < 3) {
      dispatch({ type: 'SET_FAVORITE_GENRES', genres: [...current, genreId] });
    }
  }, [state.data.favoriteGenres]);

  // Persistence helpers
  const clearDraft = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const hasDraft = useCallback(() => {
    const draft = loadDraft();
    return draft !== null && draft.currentStep !== 'genres';
  }, []);

  const value: OnboardingContextValue = {
    state,
    dispatch,
    goToStep,
    goNext,
    goBack,
    currentStepIndex,
    totalSteps,
    progress,
    canGoBack,
    canGoNext,
    updateGenres,
    toggleGenre,
    clearDraft,
    hasDraft,
  };

  return <OnboardingContext.Provider value={value}>{children}</OnboardingContext.Provider>;
}

// Hook
export function useOnboarding() {
  const context = useContext(OnboardingContext);
  if (!context) {
    throw new Error('useOnboarding must be used within an OnboardingProvider');
  }
  return context;
}
