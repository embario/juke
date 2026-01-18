export type LoginPayload = {
  username: string;
  password: string;
};

export type RegisterPayload = {
  username: string;
  email: string;
  password: string;
  passwordConfirm: string;
};

export type AuthState = {
  token: string | null;
  username: string | null;
};

export type AuthContextValue = AuthState & {
  isAuthenticated: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
};
