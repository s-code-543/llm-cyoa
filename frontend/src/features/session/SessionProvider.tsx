import { createContext, useContext, type ReactNode } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";
import {
  getSession,
  login as apiLogin,
  logout as apiLogout,
  type Permission,
  type Session,
} from "../../api/session";

type Credentials = { username: string; password: string };
type Value = {
  session: Session | undefined;
  loading: boolean;
  error: Error | null;
  can: (permission: Permission) => boolean;
  login: UseMutationResult<Session, Error, Credentials>;
  logout: UseMutationResult<Session, Error, void>;
};

const SessionContext = createContext<Value | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ["session"], queryFn: getSession });
  const login = useMutation({
    mutationFn: ({ username, password }: Credentials) =>
      apiLogin(username, password),
    onSuccess: (session) => {
      cache.clear();
      cache.setQueryData(["session"], session);
    },
  });
  const logout = useMutation({
    mutationFn: apiLogout,
    onSuccess: (session) => {
      cache.clear();
      cache.setQueryData(["session"], session);
    },
  });
  const value: Value = {
    session: query.data,
    loading: query.isPending,
    error: query.error,
    can: (permission) => query.data?.permissions.includes(permission) ?? false,
    login,
    logout,
  };
  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession requires SessionProvider");
  return value;
}
