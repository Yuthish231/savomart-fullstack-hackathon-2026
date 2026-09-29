import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, Trophy } from "lucide-react";
import { useCompare, type Report } from "@/api/areas";
import { Card, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { ConfidenceBadge, ScoreDial } from "@/components/report";
import { cn } from "@/lib/cn";

type Row = { label: string; get: (r: Report) => number | null; fmt?: (v: number) => string; higherBetter?: boolean };

const ROWS: Row[] = [
  { label: "Estimated residents", get: (r) => r.metrics?.population ?? null, fmt: (v) => v.toLocaleString("en-IN") },
  { label: "Residents per km²", get: (r) => r.sub_scores?.find((s) => s.key === "demand")?.raw_value ?? null, fmt: (v) => Math.round(v).toLocaleString("en-IN") },
  { label: "Residential buildings", get: (r) => r.metrics?.residential_buildings ?? null, fmt: (v) => v.toLocaleString("en-IN") },
  {
    label: "Grocery competitors (in area)",
    get: (r) => (r.metrics ? r.metrics.competitors.kirana_convenience + r.metrics.competitors.supermarket + r.metrics.competitors.organised_chain : null),
    higherBetter: false,
  },
  { label: "Organised chain outlets", get: (r) => r.metrics?.competitors.organised_chain ?? null, higherBetter: false },
  { label: "Nearest Savomart (km)", get: (r) => r.metrics?.nearest_store.distance_km ?? null, fmt: (v) => v.toFixed(1) },
];

function best(values: (number | null)[], higherBetter = true) {
  const nums = values.filter((v): v is number => v !== null);
  if (nums.length < 2) return null;
  return higherBetter ? Math.max(...nums) : Math.min(...nums);
}

export function ComparePage() {
  const [params] = useSearchParams();
  const ids = (params.get("ids") ?? "").split(",").filter(Boolean);
  const { data, isLoading, error } = useCompare(ids);

  return (
    <div className="mx-auto max-w-7xl p-4 md:p-6">
      <Link to="/bdm/reports" className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-savo-purple">
        <ArrowLeft className="h-4 w-4" /> All reports
      </Link>
      <PageHeader title="Compare areas" subtitle="Side by side, same model. The best value in each row is highlighted." />
      {isLoading && <Spinner />}
      {error && <ErrorNote error={error} />}
      {data && (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="w-48 p-3" />
                {data.map((r) => (
                  <th key={r.id} className="p-3 text-left align-top font-normal">
                    <Link to={`/bdm/reports/${r.id}`} className="font-semibold text-slate-900 hover:text-savo-purple">{r.area_name}</Link>
                    <div className="mt-2 flex items-center gap-3">
                      {r.overall_score !== null && r.grade && <ScoreDial score={r.overall_score} grade={r.grade} size={76} />}
                      <ConfidenceBadge level={r.confidence} />
                    </div>
                    {r.overall_score === best(data.map((x) => x.overall_score)) && (
                      <div className="mt-1 inline-flex items-center gap-1 rounded bg-savo-purple px-1.5 py-0.5 text-xs font-semibold text-savo-yellow">
                        <Trophy className="h-3 w-3" /> Best overall fit
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data[0]?.sub_scores?.map((spec) => {
                const vals = data.map((r) => r.sub_scores?.find((s) => s.key === spec.key)?.score ?? null);
                const top = best(vals);
                return (
                  <tr key={spec.key} className="border-b border-slate-50">
                    <td className="p-3 text-slate-600">{spec.label} <span className="text-xs text-slate-400">({Math.round(spec.weight * 100)}%)</span></td>
                    {vals.map((v, i) => (
                      <td key={i} className="p-3">
                        {v !== null && (
                          <div className="flex items-center gap-2">
                            <div className="h-2 w-24 rounded-full bg-slate-100">
                              <div className={cn("h-2 rounded-full", v === top ? "bg-savo-purple" : "bg-slate-300")} style={{ width: `${v}%` }} />
                            </div>
                            <span className={cn("tabular-nums", v === top && "font-bold text-savo-purple")}>{Math.round(v)}</span>
                          </div>
                        )}
                      </td>
                    ))}
                  </tr>
                );
              })}
              {ROWS.map((row) => {
                const vals = data.map(row.get);
                const top = row.label.startsWith("Nearest") ? null : best(vals, row.higherBetter ?? true);
                return (
                  <tr key={row.label} className="border-b border-slate-50">
                    <td className="p-3 text-slate-600">{row.label}</td>
                    {vals.map((v, i) => (
                      <td key={i} className={cn("p-3 tabular-nums", v !== null && v === top && "font-bold text-savo-purple")}>
                        {v === null ? "–" : row.fmt ? row.fmt(v) : v}
                      </td>
                    ))}
                  </tr>
                );
              })}
              <tr>
                <td className="p-3 text-xs text-slate-400">Report run</td>
                {data.map((r) => (
                  <td key={r.id} className="p-3 text-xs text-slate-400">
                    {new Date(r.created_at).toLocaleDateString("en-IN")} · model {r.scoring_version}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
