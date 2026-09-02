import { FormEvent, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import Button from '@uikit/components/Button';
import InputField from '@uikit/components/InputField';
import StatusBanner from '@uikit/components/StatusBanner';
import { resetPasswordRequest } from '../api/authApi';

const ResetPasswordConfirmRoute = () => {
  const [params] = useSearchParams();
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const userId = params.get('user_id');
    const timestamp = params.get('timestamp');
    const signature = params.get('signature');
    if (!userId || !timestamp || !signature) {
      setError('This reset link is incomplete or expired.');
      return;
    }
    if (!password || password !== confirmation) {
      setError('Enter the same new password twice.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await resetPasswordRequest({
        userId,
        timestamp,
        signature,
        password,
        passwordConfirm: confirmation,
      });
      setMessage('Your password has been reset. Return to your Juke app and sign in again.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to reset the password.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="auth-grid">
      <form className="card" onSubmit={submit} noValidate>
        <div className="card__body">
          <h2>Choose a new password</h2>
          <InputField name="password" label="New password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          <InputField name="passwordConfirm" label="Confirm new password" type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
          <StatusBanner variant="success" message={message} />
          <StatusBanner variant="error" message={error} />
          <div className="login-form__actions">
            <Button type="submit" disabled={submitting || Boolean(message)} data-variant="primary">
              {submitting ? 'Resetting…' : 'Reset password'}
            </Button>
            {message ? <a className="btn btn-link login-form__link" href="/accounts/login">Sign in</a> : null}
          </div>
        </div>
      </form>
    </section>
  );
};

export default ResetPasswordConfirmRoute;
