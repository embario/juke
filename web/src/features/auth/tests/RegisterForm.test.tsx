import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RegisterForm from '../components/RegisterForm';

describe('RegisterForm', () => {
  it('prevents submission when passwords mismatch', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn().mockResolvedValue(undefined);
    render(<RegisterForm onSubmit={handleSubmit} />);

    await act(async () => {
      await user.type(screen.getByPlaceholderText('auditor'), 'newuser');
      await user.type(screen.getByPlaceholderText('you@juke.fm'), 'email@example.com');
      const passwordFields = screen.getAllByPlaceholderText('••••••••');
      await user.type(passwordFields[0], 'alpha');
      await user.type(passwordFields[1], 'beta');
      await user.click(screen.getByRole('button', { name: /create account/i }));
    });

    expect(screen.getByText('Passwords must match exactly.')).toBeInTheDocument();
    expect(handleSubmit).not.toHaveBeenCalled();
  });

  it('submits matching passwords', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn().mockResolvedValue(undefined);
    render(<RegisterForm onSubmit={handleSubmit} />);

    await act(async () => {
      await user.type(screen.getByPlaceholderText('auditor'), 'newuser');
      await user.type(screen.getByPlaceholderText('you@juke.fm'), 'email@example.com');
      const passwordFields = screen.getAllByPlaceholderText('••••••••');
      await user.type(passwordFields[0], 'alpha123');
      await user.type(passwordFields[1], 'alpha123');
      await user.click(screen.getByRole('button', { name: /create account/i }));
    });

    expect(handleSubmit).toHaveBeenCalled();
  });
});
