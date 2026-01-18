import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import LoginForm from '../components/LoginForm';
import { useAuth } from '../hooks/useAuth';
import type { LoginPayload } from '../types';

const LoginRoute = () => {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleSubmit = async (payload: LoginPayload) => {
    setIsSubmitting(true);
    setError(null);
    try {
      await login(payload);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to authenticate.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="auth-grid">
      <div>
        <p className="eyebrow">Access control</p>
        <h2>Sign in to monitor the catalog</h2>
        <p className="muted">Use the credentials you registered or received via invite.</p>
      </div>
      <LoginForm onSubmit={handleSubmit} isSubmitting={isSubmitting} serverError={error} />
    </section>
  );
};

export default LoginRoute;
