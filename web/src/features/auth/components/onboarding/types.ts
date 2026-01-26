/**
 * Onboarding Types
 *
 * Type definitions for the onboarding wizard state and data structures.
 */

export type OnboardingStep =
  | 'genres'
  | 'artist'
  | 'hated'
  | 'rainy'
  | 'workout'
  | 'decade'
  | 'listening'
  | 'age'
  | 'location'
  | 'connect';

export type Genre = {
  id: string;
  name: string;
  spotifyId: string;
  topArtists: {
    name: string;
    imageUrl: string;
  }[];
};

export type Artist = {
  id: string;
  name: string;
  spotifyId: string;
  imageUrl: string;
  genres: string[];
};

export type CityLocation = {
  name: string;
  country: string;
  lat: number;
  lng: number;
};

export type MoodOption = {
  id: string;
  label: string;
  icon: string;
  genre: string;
};

export type WorkoutVibe = {
  id: string;
  label: string;
  icon: string;
  description: string;
};

export type Decade = '60s' | '70s' | '80s' | '90s' | '2000s' | '2010s' | '2020s';

export type ListeningStyle = 'playlist' | 'album';

export type AgeRange = '18-24' | '25-34' | '35-44' | '45-54' | '55+';

export type OnboardingData = {
  // Core music identity
  favoriteGenres: string[];
  rideOrDieArtist: Artist | null;
  hatedGenres: string[];

  // Contextual preferences
  rainyDayMood: string | null;
  workoutVibe: string | null;
  favoriteDecade: Decade | null;
  listeningStyle: ListeningStyle | null;

  // About you
  ageRange: AgeRange | null;
  location: CityLocation | null;

  // Spotify connection
  spotifyConnected: boolean;
};

export type OnboardingState = {
  currentStep: OnboardingStep;
  data: OnboardingData;
  isSubmitting: boolean;
  error: string | null;
  completedAt: string | null;
};

export type OnboardingAction =
  | { type: 'SET_STEP'; step: OnboardingStep }
  | { type: 'SET_FAVORITE_GENRES'; genres: string[] }
  | { type: 'SET_RIDE_OR_DIE_ARTIST'; artist: Artist | null }
  | { type: 'SET_HATED_GENRES'; genres: string[] }
  | { type: 'SET_RAINY_DAY_MOOD'; mood: string | null }
  | { type: 'SET_WORKOUT_VIBE'; vibe: string | null }
  | { type: 'SET_FAVORITE_DECADE'; decade: Decade | null }
  | { type: 'SET_LISTENING_STYLE'; style: ListeningStyle | null }
  | { type: 'SET_AGE_RANGE'; range: AgeRange | null }
  | { type: 'SET_LOCATION'; location: CityLocation | null }
  | { type: 'SET_SPOTIFY_CONNECTED'; connected: boolean }
  | { type: 'SET_SUBMITTING'; isSubmitting: boolean }
  | { type: 'SET_ERROR'; error: string | null }
  | { type: 'MARK_COMPLETE' }
  | { type: 'RESET' };

// Step configuration
export const ONBOARDING_STEPS: OnboardingStep[] = [
  'genres',
  'artist',
  'hated',
  'rainy',
  'workout',
  'decade',
  'listening',
  'age',
  'location',
  'connect',
];

export const STEP_CONFIG: Record<OnboardingStep, { title: string; subtitle: string; required: boolean }> = {
  genres: {
    title: 'What are your top 3 genres?',
    subtitle: 'These help us understand your musical identity',
    required: true,
  },
  artist: {
    title: 'Your ride-or-die artist?',
    subtitle: "That one artist you'll defend to the end",
    required: false,
  },
  hated: {
    title: "Any genres you can't stand?",
    subtitle: "We'll make sure to avoid these",
    required: false,
  },
  rainy: {
    title: "What's your rainy day soundtrack?",
    subtitle: 'When the mood is mellow',
    required: false,
  },
  workout: {
    title: 'What powers your workout?',
    subtitle: 'Your energy anthem',
    required: false,
  },
  decade: {
    title: 'What decade speaks to you?',
    subtitle: 'The era that shaped your taste',
    required: false,
  },
  listening: {
    title: 'How do you listen?',
    subtitle: 'Everyone has their style',
    required: false,
  },
  age: {
    title: "What's your age range?",
    subtitle: 'Helps us personalize your experience',
    required: false,
  },
  location: {
    title: 'Where are you located?',
    subtitle: "We'll place you on the Juke World map",
    required: false,
  },
  connect: {
    title: "You're almost there!",
    subtitle: 'Connect Spotify to complete your profile',
    required: false,
  },
};

// Preset options
export const RAINY_DAY_MOODS: MoodOption[] = [
  { id: 'mellow', label: 'Mellow & Acoustic', icon: '🌧️', genre: 'acoustic' },
  { id: 'jazz', label: 'Jazz & Lo-fi', icon: '☕', genre: 'jazz' },
  { id: 'indie', label: 'Indie & Chill', icon: '🌿', genre: 'indie' },
  { id: 'classical', label: 'Classical & Ambient', icon: '🎻', genre: 'classical' },
  { id: 'rnb', label: 'R&B & Soul', icon: '💜', genre: 'r&b' },
];

export const WORKOUT_VIBES: WorkoutVibe[] = [
  { id: 'intense', label: 'Maximum Intensity', icon: '🔥', description: 'Heavy bass, fast tempo' },
  { id: 'hiphop', label: 'Hip-Hop Energy', icon: '💪', description: 'Beats that hit hard' },
  { id: 'rock', label: 'Rock Power', icon: '🎸', description: 'Guitar-driven adrenaline' },
  { id: 'edm', label: 'EDM Drops', icon: '⚡', description: 'Build-ups and releases' },
  { id: 'pop', label: 'Pop Anthems', icon: '🎤', description: 'Sing-along motivation' },
];

export const DECADES: { id: Decade; label: string; vibe: string }[] = [
  { id: '60s', label: '60s', vibe: 'Psychedelic & Soul' },
  { id: '70s', label: '70s', vibe: 'Disco & Punk' },
  { id: '80s', label: '80s', vibe: 'Synth & New Wave' },
  { id: '90s', label: '90s', vibe: 'Grunge & Golden Era' },
  { id: '2000s', label: '2000s', vibe: 'Pop Punk & Crunk' },
  { id: '2010s', label: '2010s', vibe: 'EDM & Streaming' },
  { id: '2020s', label: '2020s', vibe: 'Hyperpop & Revival' },
];

export const AGE_RANGES: AgeRange[] = ['18-24', '25-34', '35-44', '45-54', '55+'];
