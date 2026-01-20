import { Link, useNavigate } from 'react-router-dom';
import Button from '@uikit/components/Button';
import { useAuth } from '../../auth/hooks/useAuth';
import { SPOTIFY_AUTH_PATH } from '../../auth/constants';

const Header = () => {
  const { isAuthenticated, username, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleOpenPrivateProfile = () => {
    navigate('/profiles');
  };

  return (
    <header className="app-header">
      <div>
        <p className="eyebrow">Curated by Juke</p>
        <h1>Music Intelligence Console</h1>
      </div>
      <div className="header__actions">
        {isAuthenticated ? (
          <>
            <button
              type="button"
              className="pill pill--link"
              onClick={handleOpenPrivateProfile}
              aria-label="Open private music profile"
            >
              {username ?? 'Profile'}
            </button>
            <a
              className="pill pill--accent"
              href={SPOTIFY_AUTH_PATH}
              aria-label="Connect Spotify account"
            >
              Connect Spotify
            </a>
            <Button variant="ghost" onClick={handleLogout} aria-label="Sign out">
              Sign out
            </Button>
          </>
        ) : (
          <>
            <Link to="/login" className="pill">
              Sign in
            </Link>
            <Link to="/register" className="pill pill--accent">
              Create account
            </Link>
            <a className="pill pill--accent" href={SPOTIFY_AUTH_PATH} aria-label="Sign in with Spotify">
              Sign in with Spotify
            </a>
          </>
        )}
      </div>
    </header>
  );
};

export default Header;
