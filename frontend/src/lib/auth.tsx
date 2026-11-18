// Connexion du personnel (conseiller, ml, admin) : jeton de 15 minutes, gardé dans
// sessionStorage (fermé avec l'onglet), déconnexion automatique à l'expiration.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, ApiError, type RequestOptions } from "../api/client";
import type { Role, TokenOut } from "../api/types";
import { readJson, removeKey, writeJson } from "./storage";

export interface StaffUser {
  username: string;
  role: Role;
  token: string;
  expiresAt: number;
}

interface AuthState {
  user: StaffUser | null;
  notice: string | null;
  login: (username: string, password: string) => Promise<StaffUser>;
  logout: (reason?: string) => void;
}

const KEY = "darijacare.staff";
export const EXPIRED = "Session expirée : reconnectez-vous.";

const AuthContext = createContext<AuthState | null>(null);

function storedUser(): StaffUser | null {
  const user = readJson<StaffUser | null>("session", KEY, null);
  return user && user.expiresAt > Date.now() ? user : null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<StaffUser | null>(storedUser);
  const [notice, setNotice] = useState<string | null>(null);

  const logout = useCallback((reason?: string) => {
    removeKey("session", KEY);
    setUser(null);
    setNotice(reason ?? null);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const token = await api<TokenOut>("/auth/login", {
      method: "POST",
      body: { username, password },
    });
    const next: StaffUser = {
      username,
      role: token.role,
      token: token.access_token,
      expiresAt: Date.now() + token.expires_in * 1000,
    };
    writeJson("session", KEY, next);
    setUser(next);
    setNotice(null);
    return next;
  }, []);

  useEffect(() => {
    if (!user) return undefined;
    const timer = window.setTimeout(
      () => logout(EXPIRED),
      Math.max(0, user.expiresAt - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [user, logout]);

  const value = useMemo(() => ({ user, notice, login, logout }), [user, notice, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth doit être utilisé dans AuthProvider");
  return context;
}

/** Appels authentifiés ; un 401 (jeton expiré, compte désactivé) déconnecte. */
export function useStaffApi(): <T>(path: string, options?: RequestOptions) => Promise<T> {
  const { user, logout } = useAuth();
  return useCallback(
    async <T,>(path: string, options: RequestOptions = {}): Promise<T> => {
      try {
        return await api<T>(path, { ...options, token: user?.token });
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) logout(EXPIRED);
        throw error;
      }
    },
    [user, logout],
  );
}

/** Page d'accueil de chaque rôle après connexion. */
export function homeOf(role: Role): string {
  return role === "conseiller" ? "/console" : "/tableau-de-bord";
}
