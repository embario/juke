import { FormEvent, useState } from 'react';
import Button from '@uikit/components/Button';
import InputField from '@uikit/components/InputField';
import StatusBanner from '@uikit/components/StatusBanner';
import type { RegisterPayload } from '../types';

type Props = {
  onSubmit: (payload: RegisterPayload) => Promise<void> | void;
  onResendVerification?: (email: string) => Promise<void> | void;
  isSubmitting?: boolean;
  isDisabled?: boolean;
  isResending?: boolean;
  showResendAction?: boolean;
  serverError?: string | null;
  successMessage?: string | null;
  resendMessage?: string | null;
  resendError?: string | null;
};

type FormErrors = Partial<Record<keyof RegisterPayload, string>>;

const RegisterForm = ({
  onSubmit,
  onResendVerification,
  isSubmitting = false,
  isDisabled = false,
  isResending = false,
  showResendAction = false,
  serverError = null,
  successMessage = null,
  resendMessage = null,
  resendError = null,
}: Props) => {
  const [form, setForm] = useState<RegisterPayload>({
    username: '',
    email: '',
    password: '',
    passwordConfirm: '',
  });
  const [errors, setErrors] = useState<FormErrors>({});

  const validate = () => {
    const newErrors: FormErrors = {};
    if (!form.username) newErrors.username = 'Pick a username to continue.';
    if (!form.email) newErrors.email = 'Email is required.';
    if (!form.password) newErrors.password = 'Create a password.';
    if (form.password !== form.passwordConfirm) {
      newErrors.passwordConfirm = 'Passwords must match exactly.';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isDisabled) {
      return;
    }
    if (!validate()) {
      return;
    }
    onSubmit(form);
  };

  return (
    <form className="card" onSubmit={handleSubmit} noValidate>
      <div className="card__body">
        <h2>Join the Juke Community</h2>
        <p className="muted" style={{ marginBottom: '8px' }}>
          After you sign up, we&apos;ll help you build your music identity and place you on the global map of music lovers.
        </p>
        <p className="muted" style={{ fontSize: '12px', opacity: 0.7 }}>
          Verification arrives via email moments after submission.
        </p>
        <InputField
          name="username"
          label="Username"
          placeholder="auditor"
          value={form.username}
          error={errors.username}
          disabled={isDisabled}
          onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))}
        />
        <InputField
          name="email"
          label="Email"
          type="email"
          placeholder="you@juke.fm"
          value={form.email}
          error={errors.email}
          disabled={isDisabled}
          onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
        />
        <InputField
          name="password"
          label="Password"
          type="password"
          placeholder="••••••••"
          value={form.password}
          error={errors.password}
          disabled={isDisabled}
          onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
        />
        <InputField
          name="passwordConfirm"
          label="Confirm password"
          type="password"
          placeholder="••••••••"
          value={form.passwordConfirm}
          error={errors.passwordConfirm}
          disabled={isDisabled}
          onChange={(event) => setForm((prev) => ({ ...prev, passwordConfirm: event.target.value }))}
        />
        <StatusBanner variant="success" message={successMessage} />
        <StatusBanner variant="success" message={resendMessage} />
        <StatusBanner variant="error" message={serverError} />
        <StatusBanner variant="error" message={resendError} />
        {showResendAction && onResendVerification ? (
          <Button
            type="button"
            variant="link"
            disabled={isResending || isDisabled || !form.email}
            onClick={() => onResendVerification(form.email)}
          >
            {isResending ? 'Resending…' : 'Resend verification email'}
          </Button>
        ) : null}
        <Button type="submit" disabled={isSubmitting || isDisabled} data-variant="primary">
          {isDisabled ? 'Registration disabled' : isSubmitting ? 'Submitting…' : 'Create account'}
        </Button>
        <a className="btn btn-link login-form__link" href="/login">
          Already have an account? Sign in
        </a>
      </div>
    </form>
  );
};

export default RegisterForm;
