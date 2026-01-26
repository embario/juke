/**
 * OnboardingRoute
 *
 * Route wrapper for the onboarding wizard.
 * Redirects to login if not authenticated.
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import OnboardingWizard from '../components/onboarding/OnboardingWizard';

export default function OnboardingRoute() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  if (!isAuthenticated) {
    return null;
  }

  return <OnboardingWizard />;
}
