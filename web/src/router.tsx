import { createBrowserRouter } from 'react-router-dom';
import AppLayout from './features/app/components/AppLayout';
import LoginRoute from './features/auth/routes/LoginRoute';
import RegisterRoute from './features/auth/routes/RegisterRoute';
import VerifyUserRoute from './features/auth/routes/VerifyUserRoute';
import LibraryRoute from './features/catalog/routes/LibraryRoute';
import MusicProfileRoute from './features/profiles/routes/MusicProfileRoute';
import NotFoundRoute from './features/app/routes/NotFoundRoute';
import JukeWorldRoute from './features/world/routes/JukeWorldRoute';
import OnboardingVisualizations from './features/auth/components/onboarding/visualizations';
import OnboardingRoute from './features/auth/routes/OnboardingRoute';
import MessageDesignLabRoute from './features/messages/routes/MessageDesignLabRoute';
import PasswordResetRoute from './features/auth/routes/PasswordResetRoute';
import ResetPasswordConfirmRoute from './features/auth/routes/ResetPasswordConfirmRoute';

const router = createBrowserRouter(
  [
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
          path: 'accounts/login',
          element: <LoginRoute />,
        },
        {
          path: 'register',
          element: <RegisterRoute />,
        },
        {
          path: 'accounts/signup',
          element: <RegisterRoute />,
        },
        {
          path: 'accounts/password/reset',
          element: <PasswordResetRoute />,
        },
        {
          path: 'reset-password',
          element: <ResetPasswordConfirmRoute />,
        },
        {
          path: 'verify-user/',
          element: <VerifyUserRoute />,
        },
        {
          path: 'profiles',
          element: <MusicProfileRoute />,
        },
        {
          path: 'profiles/:username',
          element: <MusicProfileRoute />,
        },
        {
          path: 'messages-lab',
          element: <MessageDesignLabRoute />,
        },
      ],
    },
    {
      path: '/world',
      element: <JukeWorldRoute />,
    },
    {
      path: '/onboarding',
      element: <OnboardingRoute />,
    },
    {
      path: '/onboarding-demo',
      element: <OnboardingVisualizations />,
    },
    {
      path: '*',
      element: <NotFoundRoute />,
    },
  ],
);

export default router;
