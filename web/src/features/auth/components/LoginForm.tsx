import { FormEvent, useState } from 'react';
import Button from '@uikit/components/Button';
import InputField from '@uikit/components/InputField';
import StatusBanner from '@uikit/components/StatusBanner';
import { SPOTIFY_AUTH_PATH } from '../constants';
import type { LoginPayload } from '../types';

type Props = {
  onSubmit: (payload: LoginPayload) => Promise<void> | void;
  isSubmitting?: boolean;
  serverError?: string | null;
};

type FormErrors = Partial<Record<keyof LoginPayload, string>>;

const LoginForm = ({ onSubmit, isSubmitting = false, serverError = null }: Props) => {
  const [form, setForm] = useState<LoginPayload>({ username: '', password: '' });
  const [errors, setErrors] = useState<FormErrors>({});

  const validate = () => {
    const newErrors: FormErrors = {};
    if (!form.username) {
      newErrors.username = 'Username is required.';
    }
    if (!form.password) {
      newErrors.password = 'Password is required.';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!validate()) {
      return;
    }
    onSubmit(form);
  };

  return (
    <form className="card" onSubmit={handleSubmit} noValidate>
      <div className="card__body">
        <h2>Welcome back</h2>
        <p className="muted">Authenticate with your catalog credentials.</p>
        <InputField
          name="username"
          label="Username"
          placeholder="analyst@juke"
          value={form.username}
          error={errors.username}
          onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))}
        />
        <InputField
          name="password"
          label="Password"
          type="password"
          placeholder="••••••••"
          value={form.password}
          error={errors.password}
          onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
        />
        <StatusBanner variant="error" message={serverError} />
        <div className="login-form__actions">
          <Button type="submit" disabled={isSubmitting} data-variant="primary">
            {isSubmitting ? 'Authenticating…' : 'Sign in'}
          </Button>
          <a className="btn btn-ghost login-form__spotify" href={SPOTIFY_AUTH_PATH} aria-label="Sign in with Spotify">
            Sign in with Spotify
          </a>
        </div>
      </div>
    </form>
  );
};

export default LoginForm;
