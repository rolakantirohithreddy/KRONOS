import { useEffect, useSyncExternalStore } from 'react';
import api from '../lib/axios';

interface User {
  email: string;
  is_verified: boolean;
  created_at: string;
}

export function useAuth() {
  const auth = useSyncExternalStore(subscribe, getAuthState, getAuthState);

  useEffect(() => {
    void fetchUser();
  }, [auth.token]);

  return { ...auth, login, logout, fetchUser };
}

interface AuthState {
  user: User | null;
  loading: boolean;
  token: string | null;
}

let authState: AuthState = {
  user: null,
  loading: Boolean(localStorage.getItem('kronos_token')),
  token: localStorage.getItem('kronos_token'),
};
const listeners = new Set<() => void>();
let userRequest: Promise<void> | null = null;
let userRequestToken: string | null = null;

function getAuthState() {
  return authState;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function updateAuthState(nextState: AuthState) {
  authState = nextState;
  listeners.forEach((listener) => listener());
}

function login(accessToken: string) {
  localStorage.setItem('kronos_token', accessToken);
  updateAuthState({ user: null, loading: true, token: accessToken });
}

function logout() {
  localStorage.removeItem('kronos_token');
  sessionStorage.removeItem('kronos_token');
  userRequest = null;
  userRequestToken = null;
  updateAuthState({ user: null, loading: false, token: null });
}

function fetchUser(): Promise<void> {
  const token = authState.token;
  if (!token) {
    if (authState.loading) updateAuthState({ ...authState, loading: false });
    return Promise.resolve();
  }
  if (userRequest && userRequestToken === token) return userRequest;

  userRequestToken = token;
  const request = api.get('/auth/me')
    .then((res) => {
      if (authState.token === token) {
        updateAuthState({ ...authState, user: res.data, loading: false });
      }
    })
    .catch(() => {
      if (authState.token === token) {
        localStorage.removeItem('kronos_token');
        updateAuthState({ user: null, loading: false, token: null });
      }
    })
    .finally(() => {
      if (userRequest === request) {
        userRequest = null;
        userRequestToken = null;
      }
    });
  userRequest = request;
  return request;
}
