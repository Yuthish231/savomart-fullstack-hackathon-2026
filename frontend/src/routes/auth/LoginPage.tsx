import { Navigate, useNavigate } from "react-router-dom";
import { Briefcase, ClipboardList, Footprints, Map as MapIcon } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useDemoLogin, usePersonas } from "@/api/auth";
import type { Role } from "@/api/types";
import { HOME } from "@/app/nav";
import { Logo } from "@/components/Logo";
import { ErrorNote, Spinner } from "@/components/ui";
import { useAuth } from "@/stores/auth";

const ROLE_INFO: Record<Role, { icon: LucideIcon; blurb: string }> = {
  BDM: { icon: MapIcon, blurb: "Explore areas, direct scouting, decide on properties" },
  BDE: { icon: Briefcase, blurb: "Scout hotspots and onboard properties from the field" },
  SM: { icon: ClipboardList, blurb: "Plan catchment studies and assign survey work" },
  SE: { icon: Footprints, blurb: "Capture lane-by-lane ground data on your phone" },
};

export function LoginPage() {
  const user = useAuth((s) => s.user);
  const personas = usePersonas();
  const login = useDemoLogin();
  const navigate = useNavigate();

  if (user) return <Navigate to={HOME[user.role]} replace />;

  return (
    <div className="min-h-full bg-gradient-to-br from-savo-purple via-savo-purple to-savo-purple-dark px-4 py-10">
      <div className="mx-auto max-w-3xl">
        <Logo />
        <h1 className="mt-8 text-3xl font-bold text-white md:text-4xl">
          Where should Savomart open next?
        </h1>
        <p className="mt-2 max-w-xl text-white/80">
          Pick a persona to enter the demo. Each one sees the product shaped around their job.
        </p>

        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          {personas.isLoading && <Spinner label="Loading personas…" />}
          {personas.error && <ErrorNote error={personas.error} />}
          {personas.data?.map((p) => {
            const { icon: Icon, blurb } = ROLE_INFO[p.role];
            return (
              <button
                key={p.username}
                onClick={() =>
                  login.mutate(p.username, { onSuccess: (r) => navigate(HOME[r.user.role]) })
                }
                disabled={login.isPending}
                className="group flex items-start gap-3 rounded-xl bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-savo-yellow disabled:opacity-60"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-savo-purple text-savo-yellow">
                  <Icon className="h-5 w-5" />
                </span>
                <span>
                  <span className="block font-semibold text-slate-900">{p.name}</span>
                  <span className="block text-xs font-semibold uppercase tracking-wide text-savo-purple">
                    {p.role_label}
                  </span>
                  <span className="mt-1 block text-sm text-slate-500">{blurb}</span>
                </span>
              </button>
            );
          })}
        </div>
        {login.error && (
          <div className="mt-4">
            <ErrorNote error={login.error} />
          </div>
        )}
      </div>
    </div>
  );
}
