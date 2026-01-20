import apiClient from '@shared/api/apiClient';
import { LoginPayload, RegisterPayload } from '../types';

type LoginResponse = {
  token: string;
};

export const loginRequest = async (payload: LoginPayload): Promise<LoginResponse> => {
  return apiClient.post<LoginResponse>('/api/v1/auth/api-auth-token/', payload);
};

export const logoutRequest = async (token: string) => {
  return apiClient.post('/api/v1/auth/session/logout/', undefined, { token });
};

export const registerRequest = async (payload: RegisterPayload) => {
  return apiClient.post('/api/v1/auth/accounts/register/', {
    username: payload.username,
    email: payload.email,
    password: payload.password,
    password_confirm: payload.passwordConfirm,
  });
};
