import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import RegisterRoute from '../routes/RegisterRoute';

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ register: vi.fn() }),
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
});
