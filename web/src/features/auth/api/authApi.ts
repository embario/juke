import apiClient from '@shared/api/apiClient';
import { LoginPayload, RegisterPayload } from '../types';

type LoginResponse = {
  token: string;
};

export const loginRequest = async (payload: LoginPayload): Promise<LoginResponse> => {
  return apiClient.post<LoginResponse>('/auth/api-auth-token/', payload);
};

export const registerRequest = async (payload: RegisterPayload) => {
  return apiClient.post('/auth/accounts/register/', {
    username: payload.username,
    email: payload.email,
    password: payload.password,
    password_confirm: payload.passwordConfirm,
  });
};
