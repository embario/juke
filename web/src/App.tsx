import { RouterProvider } from 'react-router-dom';
import router from './router';
import { AuthProvider } from './features/auth/context/AuthProvider';
import { CatalogSearchProvider } from './features/catalog/context/CatalogSearchContext';
import { PlaybackProvider } from './features/playback/context/PlaybackProvider';

const App = () => (
  <AuthProvider>
    <PlaybackProvider>
      <CatalogSearchProvider>
        <RouterProvider router={router} />
      </CatalogSearchProvider>
    </PlaybackProvider>
  </AuthProvider>
);

export default App;
