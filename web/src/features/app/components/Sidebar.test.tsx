import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

let navigateMock: ReturnType<typeof vi.fn>;
const authMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('../../auth/hooks/useAuth', () => ({
  useAuth: () => authMock(),
  default: () => authMock(),
}));

import Sidebar from './Sidebar';

const renderSidebar = () => {
  render(
    <MemoryRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <Sidebar isOpen onClose={vi.fn()} />
    </MemoryRouter>,
  );
};

describe('Sidebar', () => {
  const logoutMock = vi.fn();

  beforeEach(() => {
    navigateMock = vi.fn();
    authMock.mockReset();
    logoutMock.mockReset();
  });

  it('shows sign out button when authenticated', () => {
    authMock.mockReturnValue({ isAuthenticated: true, logout: logoutMock });

    renderSidebar();

    expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument();
  });

  it('hides sign out button when logged out', () => {
    authMock.mockReturnValue({ isAuthenticated: false, logout: logoutMock });

    renderSidebar();

    expect(screen.queryByRole('button', { name: /sign out/i })).not.toBeInTheDocument();
  });

  it('logs out and redirects on sign out', async () => {
    authMock.mockReturnValue({ isAuthenticated: true, logout: logoutMock });

    renderSidebar();

    await userEvent.click(screen.getByRole('button', { name: /sign out/i }));

    expect(logoutMock).toHaveBeenCalled();
    expect(navigateMock).toHaveBeenCalledWith('/login');
  });
});
