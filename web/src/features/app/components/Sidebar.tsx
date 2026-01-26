import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/hooks/useAuth';
import SidebarSearch from './SidebarSearch';

type Props = {
  isOpen: boolean;
  onClose: () => void;
};

const Sidebar = ({ isOpen, onClose }: Props) => {
  const { isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? 'sidebar__link sidebar__link--active' : 'sidebar__link';

  const handleNavClick = () => {
    if (typeof window !== 'undefined' && window.innerWidth <= 960) {
      onClose();
    }
  };

  const handleLogout = () => {
    logout();
    handleNavClick();
    navigate('/login');
  };

  return (
    <aside id="app-sidebar" className={`sidebar${isOpen ? ' sidebar--open' : ''}`}>
      <div className="sidebar__brand">
        <span className="sidebar__burst" />
        <strong>Juke</strong>
        <button type="button" className="sidebar__close" onClick={onClose} aria-label="Close navigation">
          x
        </button>
      </div>
      <SidebarSearch />
      <nav className="sidebar__nav">
        <NavLink to="/" end className={linkClass} onClick={handleNavClick}>
          Library
        </NavLink>
        <NavLink to="/profiles" className={linkClass} onClick={handleNavClick}>
          Music profile
        </NavLink>
        <NavLink to="/world" className={linkClass} onClick={handleNavClick}>
          Juke World
        </NavLink>
        {!isAuthenticated ? (
          <>
            <NavLink to="/login" className={linkClass} onClick={handleNavClick}>
              Sign in
            </NavLink>
            <NavLink to="/register" className={linkClass} onClick={handleNavClick}>
              Register
            </NavLink>
          </>
        ) : (
          <button type="button" className="sidebar__link sidebar__link--danger" onClick={handleLogout}>
            Sign out
          </button>
        )}
      </nav>
      <p className="sidebar__footnote">Frontend build {new Date().getFullYear()}</p>
    </aside>
  );
};

export default Sidebar;
