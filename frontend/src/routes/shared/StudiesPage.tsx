import { Link } from "react-router-dom";
import { ClipboardList } from "lucide-react";
import { useStudies, type StudySummary } from "@/api/studies";
import { useAuth } from "@/stores/auth";
import { Card, EmptyState, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { StudyStatusBadge } from "@/routes/shared/StudyPage";

/** mode "inbox": the Survey Manager's queue of studies that still need planning or fieldwork. */
export function StudiesPage({ mode = "all" }: { mode?: "all" | "inbox" }) {
  const user = useAuth((s) => s.user)!;
  const { data, isLoading, error } = useStudies();
  const base = user.role === "SM" ? "/sm/studies" : "/bdm/studies";
  const rows = (data ?? []).filter((s) => mode === "all" || ["REQUESTED", "PLANNED", "IN_PROGRESS"].includes(s.status));
  const order = { REQUESTED: 0, PLANNED: 1, IN_PROGRESS: 2, COMPLETING: 3, COMPLETED: 4 } as const;
  rows.sort((a, b) => order[a.status] - order[b.status] || b.created_at.localeCompare(a.created_at));

  return (
    <div className="mx-auto max-w-5xl p-4 md:p-6">
      <PageHeader
        title={mode === "inbox" ? "Study requests" : "Catchment studies"}
        subtitle={mode === "inbox"
          ? "New requests to split and assign, and studies in the field"
          : user.role === "BDM"
            ? "Ground surveys you've requested. Request one from a property in negotiation or from an area report."
            : "Every catchment study and where it stands"}
      />
      {isLoading && <Spinner />}
      {error && <ErrorNote error={error} />}
      {data && rows.length === 0 && (
        <EmptyState icon={<ClipboardList className="h-5 w-5" />} title={mode === "inbox" ? "Nothing waiting" : "No studies yet"}
          body={mode === "inbox" ? "New requests from the BD team appear here." : "Studies appear here once a BD Manager requests one."} />
      )}
      <div className="space-y-2">
        {rows.map((s) => <Row key={s.id} s={s} to={`${base}/${s.id}`} />)}
      </div>
    </div>
  );
}

function Row({ s, to }: { s: StudySummary; to: string }) {
  const p = s.progress;
  const closed = p.done + p.skipped + p.reused;
  return (
    <Link to={to}>
      <Card className="flex flex-wrap items-center gap-3 p-3 transition hover:shadow-md">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-mono font-semibold text-savo-purple">{s.code}</span>
            <StudyStatusBadge s={s} />
          </div>
          <div className="mt-0.5 truncate font-semibold text-slate-900">{s.title}</div>
          <div className="text-xs text-slate-500">
            {s.requested_by} · {new Date(s.created_at).toLocaleDateString("en-IN")} · {p.lanes} lanes
            {s.households_est !== null && ` · ~${s.households_est.toLocaleString("en-IN")} households`}
          </div>
        </div>
        <div className="w-40">
          <div className="h-2 rounded-full bg-slate-100">
            <div className="h-2 rounded-full bg-emerald-500" style={{ width: `${(100 * closed) / Math.max(p.lanes, 1)}%` }} />
          </div>
          <div className="mt-0.5 text-right text-xs text-slate-500">{closed}/{p.lanes} lanes</div>
        </div>
      </Card>
    </Link>
  );
}
