import { Outlet } from 'react-router-dom';
import Header from './Header';
import Sidebar from './Sidebar';
import PlaybackBar from '../../playback/components/PlaybackBar';

const AppLayout = () => (
  <div className="app-shell">
    <Sidebar />
    <div className="app-shell__content">
      <Header />
      <main>
        <Outlet />
      </main>
    </div>
    <PlaybackBar />
  </div>
);

export default AppLayout;
