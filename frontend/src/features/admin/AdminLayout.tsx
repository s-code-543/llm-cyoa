import { Label, ListBox, Select } from "@heroui/react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";

const sections = [
  ["/manage", "Dashboard", true],
  ["/manage/audit", "Audit log", false],
  ["/manage/chats", "Chats", false],
  ["/manage/configurations", "Configurations", false],
  ["/manage/prompts", "Prompts", false],
  ["/manage/providers", "Providers", false],
  ["/manage/models", "Models", false],
  ["/manage/difficulty", "Difficulty", false],
  ["/manage/voice", "Voice", false],
] as const;

export function AdminLayout() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const activeSection =
    sections.find(([to, , end]) =>
      end
        ? pathname === to || pathname === `${to}/`
        : pathname === to || pathname.startsWith(`${to}/`),
    )?.[0] ?? "/manage";
  const modelPage =
    /^\/manage\/models\/?$/.test(pathname) ||
    /^\/manage\/providers\/[^/]+\/models\/?$/.test(pathname);
  return (
    <main className="admin-layout">
      <div className="page">
        <nav className="mb-4 md:hidden" aria-label="Administration sections">
          <Select
            aria-label="Admin section"
            value={activeSection}
            onChange={(key) => {
              if (key) navigate(String(key));
            }}
            className="w-full min-w-0"
          >
            <Label>Administration</Label>
            <Select.Trigger className="min-h-11 pe-9">
              <Select.Value />
              <Select.Indicator className="end-3" />
            </Select.Trigger>
            <Select.Popover>
              <ListBox aria-label="Admin sections">
                {sections.map(([to, label]) => (
                  <ListBox.Item key={to} id={to} textValue={label}>
                    {label}
                    <ListBox.ItemIndicator />
                  </ListBox.Item>
                ))}
              </ListBox>
            </Select.Popover>
          </Select>
        </nav>
        <nav className="subnav hidden md:flex" aria-label="Administration">
          {sections.map(([to, label, end]) => (
            <NavLink key={to} to={to} end={end}>
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className={`page${modelPage ? " page--models" : ""}`}>
        <Outlet />
      </div>
    </main>
  );
}
