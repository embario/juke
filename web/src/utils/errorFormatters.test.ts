import { describe, it, expect } from 'vitest';
import { formatFieldErrors } from './errorFormatters';

describe('formatFieldErrors', () => {
  it('returns null for unsupported payloads', () => {
    expect(formatFieldErrors(null)).toBeNull();
    expect(formatFieldErrors('oops')).toBeNull();
    expect(formatFieldErrors(['error'])).toBeNull();
  });

  it('flattens field error arrays into a sentence', () => {
    const payload = {
      username: ['Already taken.'],
      email: ['Invalid email.'],
    };

    expect(formatFieldErrors(payload)).toBe('Username: Already taken. Email: Invalid email.');
  });

  it('handles non field errors gracefully', () => {
    const payload = {
      non_field_errors: ['Something broke.'],
    };

    expect(formatFieldErrors(payload)).toBe('Error: Something broke.');
  });
});
