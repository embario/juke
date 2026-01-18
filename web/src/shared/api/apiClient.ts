type RequestOptions = RequestInit & {
  token?: string | null;
  query?: Record<string, string | number | undefined>;
};

export class ApiError extends Error {
  status: number;
  payload?: unknown;

  constructor(message: string, status: number, payload?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const buildUrl = (path: string, query?: Record<string, string | number | undefined>) => {
  const url = new URL(path, API_BASE_URL);
  if (query) {
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== '') {
        url.searchParams.set(key, String(value));
      }
    });
  }
  return url.toString();
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { token, query, headers, ...rest } = options;
  const url = buildUrl(path, query);
  const response = await fetch(url, {
    ...rest,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Token ${token}` } : {}),
      ...headers,
    },
  });

  if (!response.ok) {
    const detail = await safeParse(response);
    const message = deriveErrorMessage(response.statusText, detail);
    throw new ApiError(message, response.status, detail);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json() as Promise<T>;
}

const deriveErrorMessage = (statusText: string, payload: unknown) => {
  if (payload && typeof payload === 'object' && !Array.isArray(payload) && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
  }
  return statusText;
};

async function safeParse(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch (error) {
    return undefined;
  }
}

export const apiClient = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { method: 'GET', ...options }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
      ...options,
    }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
      ...options,
    }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
      ...options,
    }),
};

export default apiClient;
