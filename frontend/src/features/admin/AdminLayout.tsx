import { NavLink, Outlet } from "react-router";

const sections = [
  ["/manage", "Dashboard", true],
  ["/manage/audit", "Audit log", false],
  ["/manage/configurations", "Configurations", false],
  ["/manage/prompts", "Prompts", false],
  ["/manage/providers", "Providers", false],
  ["/manage/models", "Models", false],
  ["/manage/difficulty", "Difficulty", false],
  ["/manage/voice", "Voice", false],
] as const;

export function AdminLayout() {
  return (
    <main className="page">
      <nav className="subnav" aria-label="Administration">
        {sections.map(([to, label, end]) => (
          <NavLink key={to} to={to} end={end}>{label}</NavLink>
        ))}
      </nav>
      <Outlet />
    </main>
  );
}
