import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, Search } from "lucide-react";
import { useProperties, type PropertySummary, type Stage } from "@/api/properties";
import { Card, EmptyState, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { FlagChips, RecPill, STAGE_LABEL, ago, inr } from "@/components/property";
import { cn } from "@/lib/cn";

const COLUMNS: Stage[] = ["SIGHTED", "EVALUATED", "SHORTLISTED", "SITE_VISIT", "NEGOTIATION", "CATCHMENT_STUDY", "FINAL_REVIEW", "APPROVED"];
const SIDE: Stage[] = ["ON_HOLD", "REJECTED"];

export function PipelinePage() {
  const { data, isLoading, error } = useProperties();
  const [q, setQ] = useState("");
  const [showClosed, setShowClosed] = useState(false);

  const byStage = useMemo(() => {
    const m = new Map<Stage, PropertySummary[]>();
    const needle = q.trim().toLowerCase();
    for (const p of data ?? []) {
      if (needle && !`${p.code} ${p.name} ${p.pincode ?? ""} ${p.created_by_name}`.toLowerCase().includes(needle)) continue;
      m.set(p.stage, [...(m.get(p.stage) ?? []), p]);
    }
    return m;
  }, [data, q]);

  const cols = showClosed ? [...COLUMNS, ...SIDE] : COLUMNS;
  const decide = (byStage.get("EVALUATED") ?? []).length;

  return (
    <div className="flex h-full flex-col p-4 md:p-6">
      <PageHeader
        title="Property pipeline"
        subtitle={decide ? `${decide} newly evaluated propert${decide === 1 ? "y needs" : "ies need"} your decision` : "Every property from first sighting to sign-off"}
        actions={
          <div className="flex items-center gap-3">
            <label className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search code, name, pincode…"
                className="min-h-9 w-56 rounded-lg border border-slate-300 pl-8 pr-2 text-sm focus:border-savo-purple focus:outline-none" />
            </label>
            <label className="flex items-center gap-1.5 text-sm text-slate-600">
              <input type="checkbox" className="accent-savo-purple" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} />
              On hold / rejected
            </label>
          </div>
        }
      />
      {isLoading && <Spinner />}
      {error && <ErrorNote error={error} />}
      {data?.length === 0 && (
        <EmptyState icon={<Building2 className="h-5 w-5" />} title="No properties yet"
          body="Assign hotspots from an area report to your executives; what they onboard lands here." />
      )}
      {data && data.length > 0 && (
        <div className="flex min-h-0 flex-1 gap-3 overflow-x-auto pb-2">
          {cols.map((s) => {
            const items = byStage.get(s) ?? [];
            return (
              <div key={s} className="flex w-64 shrink-0 flex-col rounded-xl bg-slate-100/70">
                <div className="flex items-center justify-between px-3 py-2">
                  <span className={cn("text-xs font-bold uppercase tracking-wide", s === "EVALUATED" && items.length ? "text-savo-purple" : "text-slate-500")}>
                    {STAGE_LABEL[s]}
                  </span>
                  <span className="rounded-full bg-white px-2 text-xs font-semibold text-slate-600">{items.length}</span>
                </div>
                <div className="flex-1 space-y-2 overflow-y-auto px-2 pb-2">
                  {items.map((p) => <PropertyCard key={p.id} p={p} />)}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function PropertyCard({ p }: { p: PropertySummary }) {
  return (
    <Link to={`/bdm/properties/${p.id}`}>
      <Card className="overflow-hidden transition hover:shadow-md">
        {p.cover_photo && <img src={p.cover_photo} alt="" className="h-20 w-full object-cover" />}
        <div className="p-2.5">
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-[11px] font-semibold text-savo-purple">{p.code}</span>
            <RecPill rec={p.latest_recommendation} />
          </div>
          <div className="mt-0.5 line-clamp-2 text-sm font-semibold text-slate-900">{p.name}</div>
          <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
            <span>{p.carpet_sqft ? `${p.carpet_sqft.toLocaleString("en-IN")} sq ft` : ""} · {inr(p.rent_monthly)}</span>
            {p.latest_score !== null && <span className="text-base font-bold text-slate-900">{Math.round(p.latest_score)}</span>}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">{p.created_by_name} · {ago(p.updated_at)}</div>
          {p.flags.some((f) => f.severity !== "low") && (
            <div className="mt-1.5"><FlagChips flags={p.flags.filter((f) => f.severity !== "low")} /></div>
          )}
        </div>
      </Card>
    </Link>
  );
}
