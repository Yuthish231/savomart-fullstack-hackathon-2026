import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, ChevronDown, LogOut, Users } from "lucide-react";
import { useDemoLogin, usePersonas } from "@/api/auth";
import { HOME } from "@/app/nav";
import { useAuth } from "@/stores/auth";
import { cn } from "@/lib/cn";

/** Header menu to view the app as any seeded persona (demo mode). */
export function PersonaSwitcher() {
  const user = useAuth((s) => s.user)!;
  const signOut = useAuth((s) => s.signOut);
  const personas = usePersonas();
  const login = useDemoLogin();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const switchTo = (username: string) =>
    login.mutate(username, {
      onSuccess: (res) => {
        setOpen(false);
        navigate(HOME[res.user.role]);
      },
    });

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-white hover:bg-white/10"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-savo-yellow text-xs font-bold text-savo-purple">
          {user.name
            .split(" ")
            .map((p) => p[0])
            .slice(0, 2)
            .join("")}
        </span>
        <span className="hidden leading-tight sm:block">
          <span className="block text-sm font-semibold">{user.name}</span>
          <span className="block text-[11px] text-white/70">{user.role_label}</span>
        </span>
        <ChevronDown className="h-4 w-4 text-white/70" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-2 w-72 overflow-hidden rounded-xl border border-slate-200 bg-white text-slate-800 shadow-lg"
        >
          <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <Users className="h-3.5 w-3.5" /> Switch persona (demo)
          </div>
          <div className="max-h-80 overflow-y-auto py-1">
            {personas.data?.map((p) => (
              <button
                key={p.username}
                role="menuitem"
                onClick={() => switchTo(p.username)}
                disabled={login.isPending}
                className={cn(
                  "flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-savo-purple-light",
                  p.username === user.username && "bg-savo-purple-light/60",
                )}
              >
                <span>
                  <span className="block font-medium">{p.name}</span>
                  <span className="block text-xs text-slate-500">{p.role_label}</span>
                </span>
                {p.username === user.username && <Check className="h-4 w-4 text-savo-purple" />}
              </button>
            ))}
          </div>
          <button
            onClick={() => {
              signOut();
              navigate("/login");
            }}
            className="flex w-full items-center gap-2 border-t border-slate-100 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}
