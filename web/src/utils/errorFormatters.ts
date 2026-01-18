const prettifyFieldName = (field: string): string => {
  if (field === 'non_field_errors') {
    return 'Error';
  }
  return field
    .split('_')
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ');
};

export const formatFieldErrors = (payload: unknown): string | null => {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return null;
  }

  const messages: string[] = [];
  Object.entries(payload as Record<string, unknown>).forEach(([field, value]) => {
    const label = prettifyFieldName(field);

    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (typeof item === 'string' && item.trim()) {
          messages.push(`${label}: ${item}`);
        }
      });
      return;
    }

    if (typeof value === 'string' && value.trim()) {
      messages.push(`${label}: ${value}`);
    }
  });

  return messages.length ? messages.join(' ') : null;
};
