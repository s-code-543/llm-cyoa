import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import type { Permission } from "../api/session";
import { useSession } from "../features/session/SessionProvider";

export function RequirePermission({
  permission,
  children,
}: {
  permission: Permission;
  children: ReactNode;
}) {
  const { session, loading, error, can } = useSession();
  const location = useLocation();
  if (loading)
    return (
      <p className="empty" role="status">
        Loading…
      </p>
    );
  if (error)
    return (
      <p className="empty" role="alert">
        The server is unavailable. Reload before trying again.
      </p>
    );
  if (!session?.user)
    return (
      <Navigate
        to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`}
        replace
      />
    );
  if (!can(permission))
    return (
      <div className="page" role="alert">
        <h1>Access denied</h1>
        <p>Your account does not have access to this page.</p>
      </div>
    );
  return <>{children}</>;
}
