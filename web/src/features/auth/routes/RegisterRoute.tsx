import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import RegisterForm from '../components/RegisterForm';
import { useAuth } from '../hooks/useAuth';
import type { RegisterPayload } from '../types';
import { ApiError } from '@shared/api/apiClient';
import { formatFieldErrors } from '@shared/utils/errorFormatters';
import StatusBanner from '@uikit/components/StatusBanner';

const RegisterRoute = () => {
  const { register, resendRegistrationVerification } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const [resendError, setResendError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const registrationDisabled = (() => {
    const value = import.meta.env.DISABLE_REGISTRATION ?? '';
    return ['1', 'true', 'yes', 'on'].includes(value.toLowerCase());
  })();

  const handleSubmit = async (payload: RegisterPayload) => {
    if (registrationDisabled) {
      setError('Registration is temporarily disabled. Check back soon.');
      return;
    }
    setIsSubmitting(true);
    setError(null);
    setSuccess(null);
    setResendMessage(null);
    setResendError(null);
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

  const handleResendVerification = async (email: string) => {
    if (!email) {
      setResendError('Enter your email to resend verification.');
      return;
    }
    setIsResending(true);
    setResendMessage(null);
    setResendError(null);
    try {
      await resendRegistrationVerification(email);
      setResendMessage('Verification email sent. Please check your inbox.');
    } catch (err) {
      if (err instanceof ApiError) {
        setResendError(err.message ?? 'Failed to resend verification email.');
      } else {
        setResendError(err instanceof Error ? err.message : 'Failed to resend verification email.');
      }
    } finally {
      setIsResending(false);
    }
  };

  const showResendAction = Boolean(error && /already exists|exists/i.test(error));

  useEffect(() => {
    document.body.classList.add('no-scroll');
    return () => {
      document.body.classList.remove('no-scroll');
    };
  }, []);

  return (
    <section className="auth-grid">
      {registrationDisabled ? (
        <div className="card">
          <div className="card__body">
            <StatusBanner
              variant="warning"
              message="Registration is temporarily disabled while email delivery is offline."
            />
          </div>
        </div>
      ) : (
        <RegisterForm
          onSubmit={handleSubmit}
          onResendVerification={handleResendVerification}
          isSubmitting={isSubmitting}
          isDisabled={registrationDisabled}
          isResending={isResending}
          showResendAction={showResendAction}
          serverError={error}
          successMessage={success}
          resendMessage={resendMessage}
          resendError={resendError}
        />
      )}
    </section>
  );
};

export default RegisterRoute;
