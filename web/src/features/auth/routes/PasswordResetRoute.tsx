import { FormEvent, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import Button from '@uikit/components/Button';
import InputField from '@uikit/components/InputField';
import StatusBanner from '@uikit/components/StatusBanner';
import { sendPasswordResetRequest } from '../api/authApi';

const PasswordResetRoute = () => {
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.body.classList.add('no-scroll');
    return () => document.body.classList.remove('no-scroll');
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!email.trim()) {
      setError('Email is required.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await sendPasswordResetRequest(email.trim());
      setMessage('Check your inbox to reset your password. Then return here to sign in to Juke Vibe.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to send the reset email.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="auth-grid">
      <form className="card" onSubmit={submit} noValidate>
        <div className="card__body">
          <h2>Reset your password</h2>
          <p className="muted">We’ll email the secure Juke account reset link.</p>
          <InputField
            name="email"
            label="Email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <StatusBanner variant="success" message={message} />
          <StatusBanner variant="error" message={error} />
          <div className="login-form__actions">
            <Button type="submit" disabled={submitting} data-variant="primary">
              {submitting ? 'Sending…' : 'Send reset link'}
            </Button>
            <a className="btn btn-link login-form__link" href={`/accounts/login${location.search}`}>
              Return to sign in
            </a>
          </div>
        </div>
      </form>
    </section>
  );
};

export default PasswordResetRoute;
