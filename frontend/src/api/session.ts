import { apiFetch } from "./client";

export type Permission = "play" | "admin";
export type Session = {
  user: { username: string; email: string; display_name: string } | null;
  permissions: Permission[];
};

export const getSession = () => apiFetch<Session>("/api/v1/session");
export const login = (username: string, password: string) =>
  apiFetch<Session>("/api/v1/session/login", {
    payload: { username, password },
  });
export const logout = () =>
  apiFetch<Session>("/api/v1/session/logout", { payload: {} });
