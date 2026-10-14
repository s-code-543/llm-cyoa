import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { Avatar, Button } from "@heroui/react";
import { useSession } from "../features/session/SessionProvider";
import { visibleNav } from "./nav";
import { signpostIcon } from "../assets";

function useTheme() {
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
  );
  const toggle = () => {
    const next = !dark;
    const root = document.documentElement;
    root.classList.toggle("dark", next);
    root.setAttribute("data-theme", next ? "dark" : "light");
    localStorage.setItem("theme", next ? "dark" : "light");
    setDark(next);
  };
  return { dark, toggle };
}

const pill = ({ isActive }: { isActive: boolean }) =>
  `rounded-full px-4 py-2 text-sm font-semibold transition-colors ${
    isActive
      ? "bg-brand text-white shadow-md shadow-brand/30"
      : "text-foreground/70 hover:bg-grape-soft hover:text-grape"
  }`;

export function Layout() {
  const { session, logout } = useSession();
  const { dark, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname, location.search]);
  const name = session?.user?.display_name ?? "";
  const items = visibleNav(session?.permissions ?? []);
  const signOut = () =>
    logout.mutate(undefined, {
      onSuccess: () => window.location.assign("/login"),
    });
  const themeButton = (
    <Button
      size="sm"
      variant="ghost"
      isIconOnly
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      onPress={toggle}
    >
      {dark ? "☀️" : "🌙"}
    </Button>
  );
  return (
    <div className="min-h-screen">
      <header className="top-0 z-20 px-2 pt-2 md:sticky md:px-4 md:pt-4">
        <div className="mx-auto max-w-7xl rounded-3xl border border-border bg-surface/80 shadow-lg shadow-brand/10 backdrop-blur-md md:rounded-full">
          <div className="flex items-center justify-between gap-4 py-1.5 pr-2 pl-3 md:py-2 md:pr-3 md:pl-5">
            <NavLink
              to="/"
              aria-label="Choose Your Adventure home"
              className="flex shrink-0 items-center"
            >
              <img
                src={signpostIcon}
                alt=""
                className="size-10 object-contain md:size-12"
              />
            </NavLink>
            <nav
              aria-label="Main"
              className="hidden items-center gap-1.5 md:flex"
            >
              {items.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.end} className={pill}>
                  {item.label}
                </NavLink>
              ))}
              {themeButton}
              {session?.user && (
                <>
                  <Avatar size="sm" className="ml-2">
                    <Avatar.Fallback>
                      {name.slice(0, 1).toUpperCase()}
                    </Avatar.Fallback>
                  </Avatar>
                  <span className="hidden text-sm text-muted lg:inline">
                    {name}
                  </span>
                  <Button size="sm" variant="ghost" onPress={signOut}>
                    Sign out
                  </Button>
                </>
              )}
            </nav>
            <Button
              className="md:hidden"
              size="sm"
              variant="ghost"
              isIconOnly
              aria-label="Menu"
              aria-expanded={open}
              onPress={() => setOpen((value) => !value)}
            >
              {open ? "✕" : "☰"}
            </Button>
          </div>
          {open && (
            <nav
              aria-label="Mobile"
              className="flex flex-col gap-1 border-t border-border p-2 md:hidden"
            >
              {items.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.end} className={pill}>
                  {item.label}
                </NavLink>
              ))}
              <div className="flex items-center justify-between px-2 pt-1">
                <span className="truncate text-sm text-muted">{name}</span>
                <div className="flex items-center gap-1">
                  {themeButton}
                  {session?.user && (
                    <Button size="sm" variant="ghost" onPress={signOut}>
                      Sign out
                    </Button>
                  )}
                </div>
              </div>
            </nav>
          )}
        </div>
      </header>
      <Outlet />
    </div>
  );
}
