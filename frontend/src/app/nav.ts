import type { Permission } from "../api/session";

export type NavItem = {
  to: string;
  label: string;
  permission: Permission;
  end?: boolean;
};

// Single source of truth for the menu; the API enforces the same permissions.
export const navItems: NavItem[] = [
  { to: "/", label: "Adventures", permission: "play", end: true },
  { to: "/manage", label: "Administration", permission: "admin" },
];

export const visibleNav = (permissions: Permission[]) =>
  navItems.filter((item) => permissions.includes(item.permission));
