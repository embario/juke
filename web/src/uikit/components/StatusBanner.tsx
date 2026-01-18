import { ReactNode } from 'react';
import clsx from 'clsx';

type Variant = 'info' | 'success' | 'warning' | 'error';

type Props = {
  message?: ReactNode;
  variant?: Variant;
  className?: string;
};

const variantRole: Record<Variant, 'status' | 'alert'> = {
  info: 'status',
  success: 'status',
  warning: 'status',
  error: 'alert',
};

const StatusBanner = ({ message, variant = 'info', className }: Props) => {
  if (!message) {
    return null;
  }

  return (
    <div
      className={clsx('status-banner', `status-banner--${variant}`, className)}
      role={variantRole[variant]}
      aria-live={variant === 'error' ? 'assertive' : 'polite'}
    >
      <span className="status-banner__dot" aria-hidden />
      <div className="status-banner__message">{message}</div>
    </div>
  );
};

export default StatusBanner;
