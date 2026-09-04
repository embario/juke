import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '@shared/api/apiClient';
import { formatFieldErrors } from '@shared/utils/errorFormatters';
import LoginForm from '../components/LoginForm';
import { useAuth } from '../hooks/useAuth';
import type { LoginPayload } from '../types';
import { authorizeVibeRequest, parseVibeAuthorizationRequest } from '../api/vibeAuth';

const LoginRoute = () => {
  const { login, isAuthenticated, token } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const vibeAuthorizationStarted = useRef(false);
  const redirectTo = (location.state as { redirectTo?: string } | null)?.redirectTo ?? '/';
  const vibeRequest = useMemo(
    () => parseVibeAuthorizationRequest(location.search),
    [location.search],
  );

  const oauthError = useMemo(() => {
    const params = new URLSearchParams(location.search);
    const code = params.get('error');
    if (!code) {
      return null;
    }
    switch (code) {
      case 'spotify_unavailable':
        return 'Spotify authentication is temporarily unavailable. Please try again.';
      case 'spotify_quota_exceeded':
        return 'Spotify has temporarily paused new connections because Juke reached its provider quota. Please try again later.';
      case 'spotify_connect_ticket_invalid':
        return 'This Spotify connection link expired or was already used. Start again from Juke.';
      case 'spotify_auth_failed':
        return 'Spotify authentication failed. Please try again.';
      default:
        return 'Unable to authenticate with Spotify. Please try again.';
    }
  }, [location.search]);

  useEffect(() => {
    if (isAuthenticated && !vibeRequest) {
      navigate(redirectTo, { replace: true });
    }
  }, [isAuthenticated, navigate, redirectTo, vibeRequest]);

  useEffect(() => {
    if (!isAuthenticated || !token || !vibeRequest || vibeAuthorizationStarted.current) {
      return;
    }
    vibeAuthorizationStarted.current = true;
    let active = true;
    authorizeVibeRequest(token, location.search)
      .then(({ redirect_to }) => {
        if (active) window.location.assign(redirect_to);
      })
      .catch((err) => {
        if (active) {
          vibeAuthorizationStarted.current = false;
          setError(err instanceof Error ? err.message : 'Unable to return to Juke Vibe.');
        }
      });
    return () => { active = false; };
  }, [isAuthenticated, location.search, token, vibeRequest]);

  useEffect(() => {
    document.body.classList.add('no-scroll');
    return () => {
      document.body.classList.remove('no-scroll');
    };
  }, []);

  const handleSubmit = async (payload: LoginPayload) => {
    setIsSubmitting(true);
    setError(null);
    try {
      const issuedToken = await login(payload);
      if (vibeRequest) {
        vibeAuthorizationStarted.current = true;
        const { redirect_to } = await authorizeVibeRequest(issuedToken, location.search);
        window.location.assign(redirect_to);
      } else {
        navigate(redirectTo, { replace: true });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        const fieldMessage = formatFieldErrors(err.payload);
        setError(fieldMessage ?? err.message);
      } else {
        setError(err instanceof Error ? err.message : 'Unable to authenticate.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="auth-grid">
      <LoginForm
        onSubmit={handleSubmit}
        isSubmitting={isSubmitting}
        serverError={oauthError ?? error}
        accountSearch={vibeRequest ? location.search : ''}
      />
    </section>
  );
};

export default LoginRoute;
