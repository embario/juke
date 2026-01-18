import { createBrowserRouter } from 'react-router-dom';
import AppLayout from './features/app/components/AppLayout';
import LoginRoute from './features/auth/routes/LoginRoute';
import RegisterRoute from './features/auth/routes/RegisterRoute';
import LibraryRoute from './features/catalog/routes/LibraryRoute';
import MusicProfileRoute from './features/profiles/routes/MusicProfileRoute';
import NotFoundRoute from './features/app/routes/NotFoundRoute';

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      {
        index: true,
        element: <LibraryRoute />,
      },
      {
        path: 'login',
        element: <LoginRoute />,
      },
      {
        path: 'register',
        element: <RegisterRoute />,
      },
      {
        path: 'profiles',
        element: <MusicProfileRoute />,
      },
      {
        path: 'profiles/:username',
        element: <MusicProfileRoute />,
      },
    ],
  },
  {
    path: '*',
    element: <NotFoundRoute />,
  },
]);

export default router;
