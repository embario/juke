import { Link, useNavigate } from 'react-router-dom';
import Button from '@uikit/components/Button';
import { useAuth } from '../../auth/hooks/useAuth';
import { SPOTIFY_AUTH_PATH } from '../../auth/constants';
import { requestSpotifyConnectUrl } from '../../auth/api/spotifyConnect';

type Props = {
  onToggleSidebar: () => void;
  isSidebarOpen: boolean;
};

const Header = ({ onToggleSidebar, isSidebarOpen }: Props) => {
  const { isAuthenticated, username, logout, token } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleOpenPrivateProfile = () => {
    navigate('/profiles');
  };

  const handleSpotifyConnect = async () => {
    const url = await requestSpotifyConnectUrl(token, window.location.href);
    window.location.assign(url);
  };

  return (
    <header className="app-header">
      <div className="header__title">
        <button
          type="button"
          className="mobile-nav-toggle"
          onClick={onToggleSidebar}
          aria-label={isSidebarOpen ? 'Close navigation' : 'Open navigation'}
          aria-controls="app-sidebar"
          aria-expanded={isSidebarOpen}
        >
          <span className="mobile-nav-toggle__bar" />
          <span className="mobile-nav-toggle__bar" />
          <span className="mobile-nav-toggle__bar" />
        </button>
        <h1>Juke</h1>
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
            <button
              type="button"
              className="pill pill--accent"
              onClick={() => void handleSpotifyConnect()}
              aria-label="Connect Spotify account"
            >
              Connect Spotify
            </button>
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
