import { RouterProvider } from 'react-router-dom';
import router from './router';
import { AuthProvider } from './features/auth/context/AuthProvider';
import { CatalogSearchProvider } from './features/catalog/context/CatalogSearchContext';

const App = () => (
  <AuthProvider>
    <CatalogSearchProvider>
      <RouterProvider router={router} />
    </CatalogSearchProvider>
  </AuthProvider>
);

export default App;
