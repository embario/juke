import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import ConnectStep from '../components/onboarding/steps/ConnectStep';

const navigateMock = vi.fn();
const dispatchMock = vi.fn();
const clearDraftMock = vi.fn();
let onboardingReturn = {
  state: {
    currentStep: 'connect',
    data: {
      favoriteGenres: ['rock', 'pop'],
      rideOrDieArtist: { id: '1', name: 'Artist' },
      hatedGenres: [],
      rainyDayMood: null,
      workoutVibe: null,
      favoriteDecade: '2010s',
      listeningStyle: 'playlist',
      ageRange: null,
      location: { name: 'Austin, TX', lat: 30.2672, lng: -97.7431, country: 'USA' },
      spotifyConnected: false,
    },
    isSubmitting: false,
    error: null,
    completedAt: null,
  },
  dispatch: dispatchMock,
  clearDraft: clearDraftMock,
  currentStepIndex: 9,
  totalSteps: 10,
};

vi.mock('react-router-dom', () => ({
  useNavigate: () => navigateMock,
}));

vi.mock('../components/onboarding/context/OnboardingProvider', () => ({
  useOnboarding: () => onboardingReturn,
}));

vi.mock('../components/onboarding/api/onboardingApi', () => ({
  saveOnboardingProfile: vi.fn().mockResolvedValue(undefined),
  getSpotifyOAuthUrl: vi.fn(),
}));

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ username: 'testuser' }),
}));

describe('ConnectStep', () => {
  afterEach(() => {
    navigateMock.mockReset();
  });

  it('redirects to Juke World with focus state on skip', async () => {
    onboardingReturn = {
      ...onboardingReturn,
      state: {
        ...onboardingReturn.state,
        data: {
          ...onboardingReturn.state.data,
          location: { name: 'Austin, TX', lat: 30.2672, lng: -97.7431, country: 'USA' },
        },
      },
    };
    render(<ConnectStep token="token" />);
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /skip spotify for now/i }));

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith('/world', {
        state: {
          welcomeUser: true,
          focusLat: 30.2672,
          focusLng: -97.7431,
          focusUsername: 'testuser',
        },
      });
    });
  });

  it('redirects without focus state when location is skipped', async () => {
    onboardingReturn = {
      ...onboardingReturn,
      state: {
        ...onboardingReturn.state,
        data: {
          ...onboardingReturn.state.data,
          location: null,
        },
      },
    };
    render(<ConnectStep token="token" />);
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /skip spotify for now/i }));

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith('/world', {
        state: { welcomeUser: true },
      });
    });
  });
});
