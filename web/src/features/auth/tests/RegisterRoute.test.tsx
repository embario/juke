import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import RegisterRoute from '../routes/RegisterRoute';
import { ApiError } from '@shared/api/apiClient';

const registerMock = vi.fn();
const resendMock = vi.fn();

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ register: registerMock, resendRegistrationVerification: resendMock }),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

describe('RegisterRoute', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('shows a full banner and hides the form when registration is disabled', () => {
    vi.stubEnv('DISABLE_REGISTRATION', '1');

    render(<RegisterRoute />);

    expect(
      screen.getByText('Registration is temporarily disabled while email delivery is offline.')
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Username')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /create account/i })).not.toBeInTheDocument();
  });

  it('shows the registration form when enabled', () => {
    vi.stubEnv('DISABLE_REGISTRATION', '0');

    render(<RegisterRoute />);

    expect(screen.getByText('Join the Juke Community')).toBeInTheDocument();
    expect(
      screen.queryByText('Registration is temporarily disabled while email delivery is offline.')
    ).not.toBeInTheDocument();
  });

  it('offers resend action on duplicate error', async () => {
    vi.stubEnv('DISABLE_REGISTRATION', '0');
    registerMock.mockRejectedValueOnce(
      new ApiError('Validation error', 400, { email: ['user with this email already exists.'] }),
    );
    resendMock.mockResolvedValueOnce(undefined);

    render(<RegisterRoute />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText('Email'), 'test@test.com');
    await user.type(screen.getByLabelText('Username'), 'testuser');
    await user.type(screen.getByLabelText('Password'), 'testpassword');
    await user.type(screen.getByLabelText('Confirm password'), 'testpassword');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    const resendButton = await screen.findByRole('button', { name: /resend verification email/i });
    await user.click(resendButton);
    await screen.findByText('Verification email sent. Please check your inbox.');

    expect(resendMock).toHaveBeenCalledWith('test@test.com');
  });
});
