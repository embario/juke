import { act, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ApiError } from '@shared/api/apiClient';
import LoginRoute from '../routes/LoginRoute';
import { authorizeVibeRequest } from '../api/vibeAuth';
import { redirectToClient } from '../api/browserRedirect';

const loginMock = vi.fn();
let authenticated = false;
let search = '';

vi.mock('../api/vibeAuth', async (original) => ({
  ...await original<typeof import('../api/vibeAuth')>(),
  authorizeVibeRequest: vi.fn(),
}));
vi.mock('../api/browserRedirect', () => ({ redirectToClient: vi.fn() }));

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    login: loginMock,
    isAuthenticated: authenticated,
    token: authenticated ? 'test-token' : null,
  }),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useLocation: () => ({
    state: null,
    search,
  }),
}));

describe('LoginRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authenticated = false;
    search = '';
  });

  const prepareSignedInCallback = () => {
    authenticated = true;
    search = `?client=juke-vibe-mac&redirect_uri=${encodeURIComponent('juke-vibe://auth/callback')}&state=test-state&code_challenge=${'a'.repeat(43)}&code_challenge_method=S256`;
    let complete!: (value: { redirect_to: string }) => void;
    vi.mocked(authorizeVibeRequest).mockReturnValue(new Promise(resolve => { complete = resolve; }));
    return () => complete({ redirect_to: 'juke-vibe://auth/callback?code=test' });
  };

  it('delivers one callback after StrictMode replays the signed-in effect', async () => {
    const complete = prepareSignedInCallback();
    render(<StrictMode><LoginRoute /></StrictMode>);
    await act(async () => complete());
    await waitFor(() => expect(redirectToClient).toHaveBeenCalledTimes(1));
    expect(authorizeVibeRequest).toHaveBeenCalledTimes(1);
    expect(redirectToClient).toHaveBeenCalledWith('juke-vibe://auth/callback?code=test');
  });

  it('does not redirect after the sign-in page is actually unmounted', async () => {
    const complete = prepareSignedInCallback();
    const view = render(<LoginRoute />);
    view.unmount();
    await act(async () => complete());
    expect(redirectToClient).not.toHaveBeenCalled();
  });

  it('shows backend field errors for failed sign-in', async () => {
    loginMock.mockRejectedValueOnce(
      new ApiError('Bad Request', 400, { non_field_errors: ['Unable to log in with provided credentials.'] }),
    );

    render(<LoginRoute />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText('Username'), 'token-user');
    await user.type(screen.getByLabelText('Password'), 'wrong-pass');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText('Error: Unable to log in with provided credentials.')).toBeInTheDocument();
  });
});
