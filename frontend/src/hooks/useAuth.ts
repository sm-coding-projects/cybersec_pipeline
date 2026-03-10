import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import { createElement } from "react";
import apiClient from "@/api/client";
import { LOCAL_STORAGE_TOKEN_KEY } from "@/utils/constants";
import type { User, TokenResponse, LoginRequest, RegisterRequest } from "@/types/api";

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const isAuthenticated = !!user;

  const fetchUser = useCallback(async () => {
    const token = localStorage.getItem(LOCAL_STORAGE_TOKEN_KEY);
    if (!token) {
      setIsLoading(false);
      return;
    }
    try {
      const { data } = await apiClient.get<User>("/auth/me");
      setUser(data);
    } catch {
      localStorage.removeItem(LOCAL_STORAGE_TOKEN_KEY);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  const login = useCallback(async (credentials: LoginRequest) => {
    const { data } = await apiClient.post<TokenResponse>(
      "/auth/login",
      credentials
    );
    localStorage.setItem(LOCAL_STORAGE_TOKEN_KEY, data.access_token);
    const { data: userData } = await apiClient.get<User>("/auth/me");
    setUser(userData);
  }, []);

  const register = useCallback(async (regData: RegisterRequest) => {
    // Backend returns UserResponse on register; login separately to get a token
    await apiClient.post<User>("/auth/register", regData);
    const { data: tokenData } = await apiClient.post<TokenResponse>("/auth/login", {
      username: regData.username,
      password: regData.password,
    });
    localStorage.setItem(LOCAL_STORAGE_TOKEN_KEY, tokenData.access_token);
    const { data: userData } = await apiClient.get<User>("/auth/me");
    setUser(userData);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(LOCAL_STORAGE_TOKEN_KEY);
    setUser(null);
  }, []);

  return createElement(
    AuthContext.Provider,
    { value: { user, isAuthenticated, isLoading, login, register, logout } },
    children
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
