import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '@shared/api/apiClient';
import { formatFieldErrors } from '@shared/utils/errorFormatters';
import LoginForm from '../components/LoginForm';
import { useAuth } from '../hooks/useAuth';
import type { LoginPayload } from '../types';
import { authorizeVibeRequest, parseVibeAuthorizationRequest } from '../api/vibeAuth';
import { redirectToClient } from '../api/browserRedirect';

const LoginRoute = () => {
  const { login, isAuthenticated, token } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const vibeAuthorizationStarted = useRef(false);
  const pendingAuthorization = useRef<{
    token: string;
    search: string;
    promise: Promise<{ redirect_to: string }>;
  } | null>(null);
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
    let active = true;
    // StrictMode replays setup/cleanup. Reuse the request, but attach a fresh
    // listener so replay cleanup cannot discard the only successful callback.
    if (pendingAuthorization.current?.token !== token || pendingAuthorization.current.search !== location.search) {
      pendingAuthorization.current = {
        token,
        search: location.search,
        promise: authorizeVibeRequest(token, location.search),
      };
    }
    pendingAuthorization.current.promise
      .then(({ redirect_to }) => {
        if (active) redirectToClient(redirect_to);
      })
      .catch((err) => {
        if (active) {
          vibeAuthorizationStarted.current = false;
          pendingAuthorization.current = null;
          setError(err instanceof Error ? err.message : 'Unable to return to the Juke app.');
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
    // The submit handler owns authorization during login; the authenticated
    // effect must not race it when the auth context updates.
    if (vibeRequest) vibeAuthorizationStarted.current = true;
    try {
      const issuedToken = await login(payload);
      if (vibeRequest) {
        vibeAuthorizationStarted.current = true;
        const { redirect_to } = await authorizeVibeRequest(issuedToken, location.search);
        redirectToClient(redirect_to);
      } else {
        navigate(redirectTo, { replace: true });
      }
    } catch (err) {
      vibeAuthorizationStarted.current = false;
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
