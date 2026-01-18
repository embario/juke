import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import RegisterForm from '../components/RegisterForm';
import { useAuth } from '../hooks/useAuth';
import type { RegisterPayload } from '../types';
import { ApiError } from '@shared/api/apiClient';
import { formatFieldErrors } from '@shared/utils/errorFormatters';

const RegisterRoute = () => {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (payload: RegisterPayload) => {
    setIsSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      await register(payload);
      setSuccess('Registration submitted! Verify your inbox before signing in.');
      setTimeout(() => navigate('/login'), 800);
    } catch (err) {
      if (err instanceof ApiError) {
        const fieldMessage = formatFieldErrors(err.payload);
        setError(fieldMessage ?? err.message ?? 'Registration failed.');
      } else {
        setError(err instanceof Error ? err.message : 'Registration failed.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="auth-grid">
      <div>
        <p className="eyebrow">Provision access</p>
        <h2>Create a new catalog operator</h2>
        <p className="muted">Your inbox will receive a verification link instantly.</p>
      </div>
      <RegisterForm
        onSubmit={handleSubmit}
        isSubmitting={isSubmitting}
        serverError={error}
        successMessage={success}
      />
    </section>
  );
};

export default RegisterRoute;
