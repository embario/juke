import { Outlet } from 'react-router-dom';
import Header from './Header';
import Sidebar from './Sidebar';

const AppLayout = () => (
  <div className="app-shell">
    <Sidebar />
    <div className="app-shell__content">
      <Header />
      <main>
        <Outlet />
      </main>
    </div>
  </div>
);

export default AppLayout;
