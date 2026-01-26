import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, type Mock } from 'vitest';
import { apiClient } from '@shared/api/apiClient';
import VerifyUserRoute from '../routes/VerifyUserRoute';

const navigateMock = vi.fn();
const authenticateWithTokenMock = vi.fn();

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: false, authenticateWithToken: authenticateWithTokenMock }),
}));

vi.mock('@shared/api/apiClient', () => ({
  apiClient: {
    post: vi.fn(),
  },
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

const mockedPost = apiClient.post as unknown as Mock;

describe('VerifyUserRoute', () => {
  afterEach(() => {
    mockedPost.mockReset();
    navigateMock.mockReset();
    authenticateWithTokenMock.mockReset();
    vi.useRealTimers();
  });

  it('authenticates and redirects to onboarding after successful verification', async () => {
    vi.useFakeTimers();
    mockedPost.mockResolvedValueOnce({ token: 'token-123', username: 'ember' });

    render(
      <MemoryRouter
        initialEntries={['/verify-user/?user_id=123&timestamp=456&signature=abc']}
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <VerifyUserRoute />
      </MemoryRouter>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(mockedPost).toHaveBeenCalledWith('/api/v1/auth/accounts/verify-registration/', {
      user_id: '123',
      timestamp: '456',
      signature: 'abc',
    });
    expect(authenticateWithTokenMock).toHaveBeenCalledWith('token-123', 'ember');
    expect(screen.getByText('Account Verified!')).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(1500);

    expect(navigateMock).toHaveBeenCalledWith('/onboarding', { replace: true, state: undefined });
  });
});
