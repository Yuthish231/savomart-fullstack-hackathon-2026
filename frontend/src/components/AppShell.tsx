import { NavLink, Outlet } from "react-router-dom";
import { NAV } from "@/app/nav";
import { Logo } from "@/components/Logo";
import { PersonaSwitcher } from "@/components/PersonaSwitcher";
import { SyncBadge } from "@/components/SyncBadge";
import { useSyncEngine } from "@/offline/sync";
import { useAuth } from "@/stores/auth";
import { cn } from "@/lib/cn";

/**
 * Desktop: purple top bar + left rail. Phone: compact top bar + bottom tab bar
 * (thumb-reachable, which matters most for the field personas BDE and SE).
 */
export function AppShell() {
  const user = useAuth((s) => s.user)!;
  const items = NAV[user.role];
  useSyncEngine(user.role === "SE");

  return (
    <div className="flex h-full flex-col">
      <header className="z-20 flex h-14 shrink-0 items-center justify-between bg-savo-purple px-3 shadow md:px-4">
        <Logo />
        <div className="flex items-center gap-2">
          {user.role === "SE" && <SyncBadge />}
          <PersonaSwitcher />
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <nav className="hidden w-52 shrink-0 flex-col gap-1 border-r border-slate-200 bg-white p-3 md:flex">
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100",
                  isActive && "bg-savo-purple-light text-savo-purple hover:bg-savo-purple-light",
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <main className="min-w-0 flex-1 overflow-y-auto pb-16 md:pb-0">
          <Outlet />
        </main>
      </div>

      <nav
        className="fixed inset-x-0 bottom-0 z-20 flex border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] md:hidden"
        aria-label="Primary"
      >
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium text-slate-500",
                isActive && "text-savo-purple",
              )
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={cn(
                    "flex h-7 w-12 items-center justify-center rounded-full",
                    isActive && "bg-savo-purple-light",
                  )}
                >
                  <Icon className="h-5 w-5" />
                </span>
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
