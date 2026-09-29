import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Columns3, FileBarChart, Map as MapIcon } from "lucide-react";
import { useReports } from "@/api/areas";
import { Badge, Button, Card, EmptyState, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { ConfidenceBadge, GRADE_TONE } from "@/components/report";
import { cn } from "@/lib/cn";

const fmtDate = (s: string) =>
  new Date(s).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" });

export function ReportsPage() {
  const { data, isLoading, error } = useReports();
  const [picked, setPicked] = useState<string[]>([]);
  const navigate = useNavigate();
  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length >= 4 ? p : [...p, id]));

  return (
    <div className="mx-auto max-w-5xl p-4 md:p-6">
      <PageHeader
        title="Area reports"
        subtitle="Every report is a timestamped snapshot of the data it used. Tick 2–4 to compare."
        actions={
          <Button disabled={picked.length < 2} onClick={() => navigate(`/bdm/compare?ids=${picked.join(",")}`)}>
            <Columns3 className="h-4 w-4" /> Compare{picked.length ? ` (${picked.length})` : ""}
          </Button>
        }
      />
      {isLoading && <Spinner />}
      {error && <ErrorNote error={error} />}
      {data?.length === 0 && (
        <EmptyState
          icon={<FileBarChart className="h-5 w-5" />}
          title="No reports yet"
          body="Pick an area on the Explore map and run an Area Fitness Report."
          action={<Link to="/bdm/explore"><Button><MapIcon className="h-4 w-4" /> Go to Explore</Button></Link>}
        />
      )}
      {data && data.length > 0 && (
        <Card className="divide-y divide-slate-100">
          {data.map((r) => (
            <div key={r.id} className="flex items-center gap-3 px-3 py-3">
              <input
                type="checkbox"
                aria-label={`Select ${r.area_name} for comparison`}
                checked={picked.includes(r.id)}
                disabled={r.status !== "completed" && r.status !== "partial"}
                onChange={() => toggle(r.id)}
                className="h-4 w-4 accent-savo-purple"
              />
              <span
                className={cn(
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-sm font-bold",
                  r.grade ? GRADE_TONE[r.grade] : "bg-slate-100 text-slate-400",
                )}
              >
                {r.grade ?? "…"}
              </span>
              <Link to={`/bdm/reports/${r.id}`} className="min-w-0 flex-1 hover:text-savo-purple">
                <div className="truncate font-semibold">{r.area_name}</div>
                <div className="text-xs text-slate-500">
                  {fmtDate(r.created_at)} · {r.area_km2.toFixed(1)} km² · {r.selection_type}
                </div>
              </Link>
              <div className="hidden text-right sm:block">
                {r.overall_score !== null && <div className="text-lg font-bold">{Math.round(r.overall_score)}</div>}
                <ConfidenceBadge level={r.confidence} />
              </div>
              {r.status !== "completed" && <Badge tone={r.status === "failed" ? "danger" : "warning"}>{r.status}</Badge>}
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
