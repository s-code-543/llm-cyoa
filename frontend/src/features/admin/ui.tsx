import type { ReactNode } from "react";
import { ApiError } from "../../api/client";

export const Loading = () => <p className="empty" role="status">Loading…</p>;

export const Failure = ({ error }: { error: Error | null }) =>
  error ? <p role="alert">{error.message}</p> : null;

export const fieldErrors = (error: Error | null): Record<string, string> =>
  error instanceof ApiError ? error.fields : {};

export function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label>
      {label}
      {children}
      {error && <span className="field-error" role="alert">{error}</span>}
    </label>
  );
}

export const asId = (value: string): number | null => (value ? Number(value) : null);
