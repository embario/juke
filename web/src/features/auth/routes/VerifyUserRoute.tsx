import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { apiClient } from '@shared/api/apiClient';

type VerificationState = 'loading' | 'success' | 'error';

export default function VerifyUserRoute() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [state, setState] = useState<VerificationState>('loading');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const verifyUser = async () => {
      const userId = searchParams.get('user_id');
      const timestamp = searchParams.get('timestamp');
      const signature = searchParams.get('signature');

      if (!userId || !timestamp || !signature) {
        setState('error');
        setErrorMessage('Invalid verification link. Missing required parameters.');
        return;
      }

      try {
        await apiClient.post('/api/v1/auth/accounts/verify-registration/', {
          user_id: userId,
          timestamp: timestamp,
          signature: signature,
        });
        setState('success');
        // Redirect to login after 3 seconds
        setTimeout(() => navigate('/login'), 3000);
      } catch (err) {
        setState('error');
        setErrorMessage(
          err instanceof Error ? err.message : 'Verification failed. The link may have expired.'
        );
      }
    };

    verifyUser();
  }, [searchParams, navigate]);

  return (
    <div className="card" style={{ maxWidth: 480, margin: '80px auto', textAlign: 'center' }}>
      <div className="card__body">
        {state === 'loading' && (
          <>
            <h2>Verifying your account...</h2>
            <p className="muted">Please wait while we confirm your email.</p>
          </>
        )}

        {state === 'success' && (
          <>
            <div style={{ fontSize: 48, marginBottom: 16 }}>✓</div>
            <h2>Account Verified!</h2>
            <p className="muted">
              Your account has been verified. Redirecting you to login...
            </p>
            <a href="/login" className="btn" data-variant="primary" style={{ marginTop: 16 }}>
              Go to Login
            </a>
          </>
        )}

        {state === 'error' && (
          <>
            <div style={{ fontSize: 48, marginBottom: 16 }}>✗</div>
            <h2>Verification Failed</h2>
            <p className="muted">{errorMessage}</p>
            <a href="/register" className="btn" data-variant="primary" style={{ marginTop: 16 }}>
              Try Again
            </a>
          </>
        )}
      </div>
    </div>
  );
}
