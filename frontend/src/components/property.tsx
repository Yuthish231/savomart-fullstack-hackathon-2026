import { useEffect, useRef, type ReactNode } from "react";
import { AlertOctagon, AlertTriangle, CheckCircle2, CircleHelp, Info, X } from "lucide-react";
import type { Flag, Recommendation, Stage } from "@/api/properties";
import { cn } from "@/lib/cn";

export const STAGE_LABEL: Record<Stage, string> = {
  SIGHTED: "Sighted",
  EVALUATED: "Evaluated",
  SHORTLISTED: "Shortlisted",
  SITE_VISIT: "Site visit",
  NEGOTIATION: "Negotiation",
  CATCHMENT_STUDY: "Catchment study",
  FINAL_REVIEW: "Final review",
  APPROVED: "Approved",
  ON_HOLD: "On hold",
  REJECTED: "Rejected",
};

export function StageBadge({ stage, className }: { stage: Stage; className?: string }) {
  const tone =
    stage === "APPROVED"
      ? "bg-emerald-600 text-white"
      : stage === "REJECTED"
        ? "bg-slate-200 text-slate-600"
        : stage === "ON_HOLD"
          ? "bg-amber-100 text-amber-800"
          : stage === "SIGHTED"
            ? "bg-slate-100 text-slate-700"
            : "bg-savo-purple-light text-savo-purple";
  return (
    <span className={cn("inline-flex rounded-full px-2 py-0.5 text-xs font-semibold", tone, className)}>
      {STAGE_LABEL[stage]}
    </span>
  );
}

const REC: Record<Recommendation, { label: string; cls: string }> = {
  proceed: { label: "Proceed", cls: "bg-emerald-600 text-white" },
  review: { label: "Review", cls: "bg-amber-500 text-white" },
  reject: { label: "Reject", cls: "bg-red-600 text-white" },
};

export function RecPill({ rec, className }: { rec: Recommendation | null; className?: string }) {
  if (!rec) return <span className="text-xs text-slate-400">evaluating…</span>;
  return (
    <span className={cn("inline-flex rounded px-2 py-0.5 text-xs font-bold uppercase tracking-wide", REC[rec].cls, className)}>
      {REC[rec].label}
    </span>
  );
}

export function SeverityIcon({ severity }: { severity?: string }) {
  if (severity === "high") return <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0 text-red-600" />;
  if (severity === "medium") return <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />;
  return <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />;
}

export function FlagChips({ flags }: { flags: Flag[] }) {
  if (!flags.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {flags.map((f) => (
        <span
          key={f.code}
          title={f.message}
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold",
            f.severity === "high" ? "bg-red-50 text-red-700" : f.severity === "medium" ? "bg-amber-50 text-amber-800" : "bg-slate-100 text-slate-600",
          )}
        >
          <AlertTriangle className="h-3 w-3" /> {f.code.replaceAll("_", " ").toLowerCase()}
        </span>
      ))}
    </div>
  );
}

export function CheckStatusIcon({ status }: { status: string }) {
  if (status === "good") return <CheckCircle2 className="h-4 w-4 text-emerald-600" />;
  if (status === "ok") return <CheckCircle2 className="h-4 w-4 text-slate-400" />;
  if (status === "blocker") return <AlertOctagon className="h-4 w-4 text-red-600" />;
  if (status === "poor") return <AlertTriangle className="h-4 w-4 text-amber-600" />;
  return <CircleHelp className="h-4 w-4 text-slate-300" />;
}

/** Accessible modal: focus trap-lite (focus first field), Esc to close, click outside to close. */
export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", k);
    // Focus the first form field (not the close button, which comes first in the DOM).
    (ref.current?.querySelector<HTMLElement>("textarea, input, select") ?? ref.current?.querySelector<HTMLElement>("button"))?.focus();
    return () => document.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4" onMouseDown={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(e) => e.stopPropagation()}
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-4 shadow-xl sm:rounded-2xl"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-slate-900">{title}</h2>
          <button onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export const inr = (v: number | null | undefined) =>
  v === null || v === undefined ? "–" : `₹${Math.round(v).toLocaleString("en-IN")}`;

export const ago = (iso: string) => {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
};
