import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ApiError } from '@shared/api/apiClient';
import LoginRoute from '../routes/LoginRoute';

const loginMock = vi.fn();

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    login: loginMock,
    isAuthenticated: false,
  }),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useLocation: () => ({
    state: null,
    search: '',
  }),
}));

describe('LoginRoute', () => {
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
