import { ButtonHTMLAttributes } from 'react';
import clsx from 'clsx';

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'ghost' | 'link';
};

const Button = ({ variant = 'primary', className, children, ...rest }: Props) => (
  <button
    className={clsx(
      'btn',
      variant === 'primary' && 'btn-primary',
      variant === 'ghost' && 'btn-ghost',
      variant === 'link' && 'btn-link',
      className,
    )}
    {...rest}
  >
    {children}
  </button>
);

export default Button;
