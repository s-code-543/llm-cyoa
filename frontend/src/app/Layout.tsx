import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import { Avatar, Button } from "@heroui/react";
import { useSession } from "../features/session/SessionProvider";
import { visibleNav } from "./nav";

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
  const name = session?.user?.display_name ?? "";
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 px-4 pt-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 rounded-full border border-border bg-surface/80 py-2 pr-3 pl-5 shadow-lg shadow-grape/10 backdrop-blur-md">
          <NavLink to="/" className="flex items-center gap-2.5">
            <span className="grid size-9 place-items-center rounded-full bg-linear-to-br from-brand via-brand-coral to-sun text-lg text-white shadow">
              ✦
            </span>
            <span className="font-story text-2xl font-bold tracking-wide text-grape">
              CYOA
            </span>
          </NavLink>
          <nav aria-label="Main" className="flex items-center gap-1.5">
            {visibleNav(session?.permissions ?? []).map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={pill}
              >
                {item.label}
              </NavLink>
            ))}
            <Button
              size="sm"
              variant="ghost"
              isIconOnly
              aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
              onPress={toggle}
            >
              {dark ? "☀️" : "🌙"}
            </Button>
            {session?.user && (
              <>
                <Avatar size="sm" className="ml-2 hidden sm:flex">
                  <Avatar.Fallback>
                    {name.slice(0, 1).toUpperCase()}
                  </Avatar.Fallback>
                </Avatar>
                <span className="hidden text-sm text-muted lg:inline">
                  {name}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onPress={() =>
                    logout.mutate(undefined, {
                      onSuccess: () => window.location.assign("/login"),
                    })
                  }
                >
                  Sign out
                </Button>
              </>
            )}
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
