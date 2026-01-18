import { NavLink } from 'react-router-dom';
import { useAuth } from '../../auth/hooks/useAuth';
import SidebarSearch from './SidebarSearch';

const Sidebar = () => {
  const { isAuthenticated } = useAuth();

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? 'sidebar__link sidebar__link--active' : 'sidebar__link';

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__burst" />
        <strong>Juke</strong>
      </div>
      <SidebarSearch />
      <nav className="sidebar__nav">
        <NavLink to="/" end className={linkClass}>
          Library
        </NavLink>
        <NavLink to="/profiles" className={linkClass}>
          Music profile
        </NavLink>
        {!isAuthenticated && (
          <>
            <NavLink to="/login" className={linkClass}>
              Sign in
            </NavLink>
            <NavLink to="/register" className={linkClass}>
              Register
            </NavLink>
          </>
        )}
      </nav>
      <p className="sidebar__footnote">Frontend build {new Date().getFullYear()}</p>
    </aside>
  );
};

export default Sidebar;
