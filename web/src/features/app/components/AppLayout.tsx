import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import Sidebar from './Sidebar';
import PlaybackBar from '../../playback/components/PlaybackBar';
import { useAuth } from '../../auth/hooks/useAuth';

const AppLayout = () => {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => {
    if (typeof window === 'undefined') {
      return true;
    }
    return window.innerWidth > 960;
  });

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) {
      return undefined;
    }
    const media = window.matchMedia('(max-width: 960px)');
    const handleChange = () => {
      if (media.matches) {
        setIsSidebarOpen(false);
      }
    };
    handleChange();
    media.addEventListener('change', handleChange);
    return () => media.removeEventListener('change', handleChange);
  }, []);

  useEffect(() => {
    const path = location.pathname;
    const isPublicRoute = path === '/login' || path === '/register';
    if (!isAuthenticated && !isPublicRoute) {
      navigate('/login', { replace: true });
    }
  }, [isAuthenticated, location.pathname, navigate]);

  const handleToggleSidebar = () => setIsSidebarOpen((current) => !current);
  const handleCloseSidebar = () => setIsSidebarOpen(false);

  const shellClass = isAuthenticated && isSidebarOpen
    ? 'app-shell app-shell--sidebar-open'
    : 'app-shell app-shell--sidebar-collapsed';

  return (
    <div className={shellClass}>
      {isAuthenticated && (
        <>
          <Sidebar isOpen={isSidebarOpen} onClose={handleCloseSidebar} />
          <button
            type="button"
            className={`sidebar-overlay${isSidebarOpen ? ' sidebar-overlay--visible' : ''}`}
            onClick={handleCloseSidebar}
            aria-label="Close navigation"
          />
        </>
      )}
      <div className="app-shell__content">
        <div className="app-shell__toolbar">
          {isAuthenticated && (
            <button
              type="button"
              className="mobile-nav-toggle"
              onClick={handleToggleSidebar}
              aria-label={isSidebarOpen ? 'Close navigation' : 'Open navigation'}
              aria-controls="app-sidebar"
              aria-expanded={isSidebarOpen}
            >
              <span className="mobile-nav-toggle__bar" />
              <span className="mobile-nav-toggle__bar" />
              <span className="mobile-nav-toggle__bar" />
            </button>
          )}
          <span className="app-shell__title">Juke</span>
        </div>
        <main>
          <Outlet />
          </main>
        </div>
      {isAuthenticated && <PlaybackBar />}
    </div>
  );
};

export default AppLayout;
