import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LoginForm from '../components/LoginForm';

describe('LoginForm', () => {
  it('submits valid credentials', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn().mockResolvedValue(undefined);
    render(<LoginForm onSubmit={handleSubmit} />);

    await act(async () => {
      await user.type(screen.getByPlaceholderText('analyst@juke'), 'analyst');
      await user.type(screen.getByPlaceholderText('••••••••'), 'password123');
      await user.click(screen.getByRole('button', { name: /sign in/i }));
    });

    expect(handleSubmit).toHaveBeenCalledWith({ username: 'analyst', password: 'password123' });
  });

  it('shows validation errors when empty', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn().mockResolvedValue(undefined);
    render(<LoginForm onSubmit={handleSubmit} />);

    await act(async () => {
      await user.click(screen.getByRole('button', { name: /sign in/i }));
    });

    expect(screen.getByText('Username is required.')).toBeInTheDocument();
    expect(screen.getByText('Password is required.')).toBeInTheDocument();
    expect(handleSubmit).not.toHaveBeenCalled();
  });
});
