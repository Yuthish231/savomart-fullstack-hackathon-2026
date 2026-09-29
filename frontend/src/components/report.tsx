import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import type { Fact, SubScore } from "@/api/areas";
import type { JobStep } from "@/api/types";
import { Badge } from "@/components/ui";
import { cn } from "@/lib/cn";

export const GRADE_TONE: Record<string, string> = {
  A: "bg-emerald-600 text-white",
  B: "bg-savo-purple text-savo-yellow",
  C: "bg-amber-500 text-white",
  D: "bg-red-600 text-white",
};

export function ScoreDial({ score, grade, size = 112 }: { score: number; grade: string; size?: number }) {
  const r = 44;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} aria-label={`Score ${score} of 100, grade ${grade}`}>
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" stroke="#F3E9F6" strokeWidth="9" />
        <circle
          cx="50" cy="50" r={r} fill="none" stroke="#782B90" strokeWidth="9" strokeLinecap="round"
          strokeDasharray={`${(score / 100) * c} ${c}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold text-slate-900">{Math.round(score)}</span>
        <span className={cn("mt-0.5 rounded px-1.5 text-xs font-bold", GRADE_TONE[grade])}>Grade {grade}</span>
      </div>
    </div>
  );
}

export function JobProgress({ steps, status }: { steps: JobStep[]; status: string }) {
  return (
    <ol className="space-y-2">
      {steps.map((s) => (
        <li key={s.name} className="flex items-start gap-2 text-sm">
          {s.status === "done" ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-600" />
          ) : s.status === "running" ? (
            <Loader2 className="mt-0.5 h-4 w-4 animate-spin text-savo-purple" />
          ) : s.status === "failed" ? (
            <XCircle className="mt-0.5 h-4 w-4 text-red-600" />
          ) : (
            <Circle className="mt-0.5 h-4 w-4 text-slate-300" />
          )}
          <span>
            <span className={cn(s.status === "pending" && "text-slate-400")}>{s.label}</span>
            {s.error && <span className="block text-xs text-red-600">{s.error}</span>}
          </span>
        </li>
      ))}
      {status === "queued" && <li className="text-xs text-slate-500">Waiting for a worker…</li>}
    </ol>
  );
}

function fmt(v: number | string, unit: string) {
  if (typeof v === "string") return v;
  const n = Math.abs(v) >= 1000 ? v.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : String(v);
  return unit && !unit.startsWith("/") && unit !== "percentile" ? `${n} ${unit}` : `${n}${unit.startsWith("/") ? unit : ""}`;
}

/** Inline citation: hover or focus to see the value, unit and source behind a claim. */
export function FactChip({ id, fact }: { id: string; fact?: Fact }) {
  if (!fact) return null;
  return (
    <span className="group relative ml-1 inline-block align-middle">
      <button
        type="button"
        className="rounded bg-savo-purple-light px-1 text-[10px] font-semibold text-savo-purple focus:outline focus:outline-1 focus:outline-savo-purple"
        aria-label={`${fact.label}: ${fmt(fact.value, fact.unit)} (${fact.source})`}
      >
        {id.replace(/^(sub|raw|pct)_/, "")}
      </button>
      <span className="pointer-events-none absolute bottom-full left-0 z-20 mb-1 hidden w-56 rounded-lg bg-slate-900 px-2 py-1.5 text-xs text-white shadow-lg group-hover:block group-focus-within:block">
        <span className="block font-semibold">{fact.label}</span>
        <span className="block">{fmt(fact.value, fact.unit)}</span>
        <span className="block text-white/60">Source: {fact.source}</span>
      </span>
    </span>
  );
}

export function SubScoreCard({ s }: { s: SubScore }) {
  const tone = s.score >= 70 ? "bg-emerald-500" : s.score >= 45 ? "bg-savo-purple" : "bg-amber-500";
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-slate-800">{s.label}</span>
        <span className="text-lg font-bold text-slate-900">{Math.round(s.score)}</span>
      </div>
      <div className="mt-1.5 h-1.5 rounded-full bg-slate-100">
        <div className={cn("h-1.5 rounded-full", tone)} style={{ width: `${s.score}%` }} />
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-[11px] text-slate-500">
        <div className="col-span-2 flex gap-1">
          <dt>Raw:</dt>
          <dd className="font-medium text-slate-700">{s.raw_value.toLocaleString("en-IN")} {s.unit}</dd>
        </div>
        <div>
          <dt>{s.percentile !== null ? "Chennai pct." : "Rule"}</dt>
          <dd className="font-medium text-slate-700">{s.percentile !== null ? `p${Math.round(s.percentile)}` : "distance band"}</dd>
        </div>
        <div>
          <dt>Weight → pts</dt>
          <dd className="font-medium text-slate-700">{Math.round(s.weight * 100)}% → {s.contribution.toFixed(1)}</dd>
        </div>
      </dl>
      <p className="mt-2 text-[11px] leading-snug text-slate-500">{s.explain}</p>
    </div>
  );
}

export function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="mt-6">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function ConfidenceBadge({ level }: { level: string | null }) {
  if (!level) return null;
  return (
    <Badge tone={level === "High" ? "success" : level === "Medium" ? "warning" : "danger"}>
      {level !== "High" && <AlertTriangle className="h-3 w-3" />} {level} confidence
    </Badge>
  );
}
