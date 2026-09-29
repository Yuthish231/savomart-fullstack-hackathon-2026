import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Layer, Source } from "react-map-gl/maplibre";
import type { FeatureCollection } from "geojson";
import { ArrowLeft, Bot, CheckCircle2, FileText, Recycle, RotateCcw, Scissors, Users } from "lucide-react";
import { useStudy, useStudyActions, useStudyLanes, type StudyDetail } from "@/api/studies";
import { useAuth } from "@/stores/auth";
import { MapView } from "@/map/MapView";
import { BRAND } from "@/map/layers";
import { Badge, Button, Card, ErrorNote, Spinner } from "@/components/ui";
import { JobProgress, Section } from "@/components/report";
import { Modal } from "@/components/property";
import { cn } from "@/lib/cn";

export const CHUNK_COLORS = ["#782B90", "#E8A317", "#0E9F8E", "#D6336C", "#3B82F6", "#65A30D", "#EA580C", "#6B7280", "#9333EA", "#0891B2", "#CA8A04", "#BE123C"];
const STATUS_COLOR: Record<string, string> = { todo: "#94a3b8", draft: "#f59e0b", done: "#10b981", skipped: "#475569", reused: "#a78bfa" };

export const STUDY_STATUS_LABEL: Record<string, string> = {
  REQUESTED: "Requested", PLANNED: "Planned", IN_PROGRESS: "In the field", COMPLETING: "Rolling up", COMPLETED: "Completed",
};

export function StudyStatusBadge({ s }: { s: Pick<StudyDetail, "status" | "reuse_mode"> }) {
  return (
    <span className="inline-flex items-center gap-1">
      <Badge tone={s.status === "COMPLETED" ? "success" : s.status === "REQUESTED" ? "warning" : "brand"}>{STUDY_STATUS_LABEL[s.status]}</Badge>
      {s.reuse_mode !== "none" && <Badge tone="highlight"><Recycle className="h-3 w-3" /> {s.reuse_mode} reuse</Badge>}
    </span>
  );
}

export function StudyPage() {
  const { id } = useParams();
  const user = useAuth((s) => s.user)!;
  const { data: s, isLoading, error } = useStudy(id);
  const version = s ? `${s.status}-${s.chunks.map((c) => c.id + c.closed).join(",")}` : "";
  const lanes = useStudyLanes(id, version);
  const act = useStudyActions(id!);
  const [colorBy, setColorBy] = useState<"chunk" | "status">("chunk");
  const [target, setTarget] = useState(3000);
  const [closeEarly, setCloseEarly] = useState(false);
  const [reason, setReason] = useState("");
  const [resurveyOpen, setResurveyOpen] = useState(false);

  const chunkIndex = useMemo(() => new Map((s?.chunks ?? []).map((c, i) => [c.label, i])), [s?.chunks]);
  const area = useMemo<FeatureCollection | null>(() => (s ? { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: s.geometry }] } : null), [s?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const bounds = useMemo(() => {
    if (!s) return undefined;
    const xs: number[] = [], ys: number[] = [];
    const walk = (c: unknown): void => { if (Array.isArray(c) && typeof c[0] === "number") { xs.push(c[0] as number); ys.push(c[1] as number); } else if (Array.isArray(c)) c.forEach(walk); };
    walk((s.geometry as { coordinates: unknown }).coordinates);
    return [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]] as [[number, number], [number, number]];
  }, [s?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading) return <div className="p-6"><Spinner label="Loading study…" /></div>;
  if (error || !s) return <div className="p-6"><ErrorNote error={error ?? new Error("Not found")} /></div>;

  const isSM = user.role === "SM";
  const p = s.progress;
  const pct = (n: number) => `${(100 * n) / Math.max(p.lanes, 1)}%`;
  const canPlan = isSM && (s.status === "REQUESTED" || s.status === "PLANNED") && s.reuse_mode !== "full";
  const colorExpr = colorBy === "status"
    ? ["match", ["get", "status"], "draft", STATUS_COLOR.draft, "done", STATUS_COLOR.done, "skipped", STATUS_COLOR.skipped, "reused", STATUS_COLOR.reused, STATUS_COLOR.todo]
    : ["match", ["coalesce", ["get", "chunk"], "-"], ...s.chunks.flatMap((c) => [c.label, CHUNK_COLORS[(chunkIndex.get(c.label) ?? 0) % CHUNK_COLORS.length]]),
      "-", "#a78bfa", "#cbd5e1"];
  const ins = s.insight;
  const back = user.role === "SM" ? "/sm/studies" : "/bdm/studies";

  return (
    <div className="mx-auto max-w-7xl p-4 md:p-6">
      <Link to={back} className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-savo-purple"><ArrowLeft className="h-4 w-4" /> Studies</Link>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_440px]">
        <div className="min-w-0 space-y-4">
          <Card className="p-4 md:p-5">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-mono font-semibold text-savo-purple">{s.code}</span>
              <StudyStatusBadge s={s} />
              <span className="text-slate-500">{s.target_type === "property" ? `${s.radius_m} m walk catchment` : `${s.radius_m} m around top hotspots`}</span>
            </div>
            <h1 className="mt-1 text-xl font-bold text-slate-900">{s.title}</h1>
            <p className="text-sm text-slate-500">
              Requested by {s.requested_by} · {new Date(s.created_at).toLocaleDateString("en-IN")}
              {s.property && <> · <Link className="text-savo-purple hover:underline" to={`/${user.role === "BDM" ? "bdm" : "bdm"}/properties/${s.property.id}`}>{s.property.code}</Link></>}
              {s.report_id && user.role === "BDM" && <> · <Link className="text-savo-purple hover:underline" to={`/bdm/reports/${s.report_id}`}>area report</Link></>}
            </p>
            {s.reuse_mode !== "none" && (
              <div className="mt-3 rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm text-violet-900">
                <Recycle className="mr-1 inline h-4 w-4" />
                {Math.round(s.reuse_coverage * 100)}% of the lane length was surveyed in the last 180 days
                ({s.reused_studies.map((r) => r.code).join(", ")}).{" "}
                {s.reuse_mode === "full" ? "No new fieldwork needed: insight built from those surveys." : "Only the remaining lanes go to the field."}
                {isSM && s.status !== "IN_PROGRESS" && s.status !== "COMPLETING" && (
                  <button onClick={() => setResurveyOpen(true)} className="ml-2 font-semibold underline">Resurvey anyway</button>
                )}
              </div>
            )}
            <div className="mt-4">
              <div className="flex h-3 overflow-hidden rounded-full bg-slate-100">
                <div className="bg-emerald-500" style={{ width: pct(p.done) }} title="done" />
                <div className="bg-slate-600" style={{ width: pct(p.skipped) }} title="skipped" />
                <div className="bg-violet-400" style={{ width: pct(p.reused) }} title="reused" />
                <div className="bg-amber-400" style={{ width: pct(p.draft) }} title="draft" />
              </div>
              <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-slate-500">
                <span>{p.lanes} lanes · {(s.total_length_m / 1000).toFixed(1)} km</span>
                <span className="text-emerald-700">{p.done} done</span>
                <span>{p.skipped} skipped</span>
                {p.reused > 0 && <span className="text-violet-700">{p.reused} reused</span>}
                {p.draft > 0 && <span className="text-amber-700">{p.draft} drafts</span>}
              </div>
            </div>
            {s.status === "COMPLETING" && s.job && <div className="mt-3 rounded-lg bg-slate-50 p-3"><JobProgress steps={s.job.steps} status={s.job.status} /></div>}
            {isSM && (s.status === "PLANNED" || s.status === "IN_PROGRESS") && (
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                <Button onClick={() => (p.closed_share >= s.can_complete_at ? act.complete.mutate(undefined) : setCloseEarly(true))} loading={act.complete.isPending}>
                  <CheckCircle2 className="h-4 w-4" /> Complete study
                </Button>
                <span className="text-xs text-slate-500">{Math.round(p.closed_share * 100)}% of lanes closed · {Math.round(s.can_complete_at * 100)}% needed</span>
              </div>
            )}
            {(act.complete.error || act.plan.error || act.assign.error) && <div className="mt-2"><ErrorNote error={act.complete.error ?? act.plan.error ?? act.assign.error} /></div>}
          </Card>

          {canPlan && (
            <Card className="p-4">
              <h2 className="flex items-center gap-2 font-semibold text-slate-900"><Scissors className="h-4 w-4 text-savo-purple" /> Split into chunks</h2>
              <p className="mt-1 text-sm text-slate-600">
                Contiguous, non-overlapping patches of similar walking effort, grown along the street network. Pick about one surveyor-session per chunk.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {[2000, 3000, 4000, 5000].map((t) => (
                  <button key={t} onClick={() => setTarget(t)} aria-pressed={target === t}
                    className={cn("rounded-full border px-3 py-1.5 text-sm", target === t ? "border-savo-purple bg-savo-purple text-white" : "border-slate-300")}>
                    ~{t / 1000} km each
                  </button>
                ))}
                <Button onClick={() => act.plan.mutate(target)} loading={act.plan.isPending}>{s.chunks.length ? "Re-split" : "Split"}</Button>
              </div>
            </Card>
          )}

          {s.chunks.length > 0 && (
            <Section title={`Work chunks (${s.chunks.length})`}>
              <Card className="divide-y divide-slate-100">
                {s.chunks.map((c, i) => (
                  <div key={c.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-sm font-bold text-white" style={{ background: CHUNK_COLORS[i % CHUNK_COLORS.length] }}>{c.label}</span>
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-slate-800">{c.lane_count} lanes · {(c.effort_m / 1000).toFixed(1)} km effort</div>
                      <div className="mt-1 h-1.5 w-40 rounded-full bg-slate-100"><div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${(100 * c.closed) / c.lane_count}%` }} /></div>
                      <div className="mt-0.5 text-xs text-slate-500">
                        {c.closed}/{c.lane_count} closed{c.drafts ? ` · ${c.drafts} drafts` : ""}
                        {c.last_sync && ` · last sync ${new Date(c.last_sync).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`}
                      </div>
                    </div>
                    {isSM && s.status !== "COMPLETED" && s.status !== "COMPLETING" ? (
                      <select value={c.assignee_id ?? ""} onChange={(e) => act.assign.mutate({ chunk: c.id, assignee: e.target.value || null })}
                        className="min-h-9 rounded-lg border border-slate-300 px-2 text-sm" aria-label={`Assign chunk ${c.label}`}>
                        <option value="">Unassigned</option>
                        {s.team.map((u) => <option key={u.id} value={u.id}>{u.name} ({u.open_chunks} open)</option>)}
                      </select>
                    ) : (
                      <span className="flex items-center gap-1 text-slate-600"><Users className="h-4 w-4" /> {c.assignee ?? "Unassigned"}</span>
                    )}
                    <Badge tone={c.status === "done" ? "success" : c.status === "in_progress" ? "brand" : "neutral"}>{c.status.replace("_", " ")}</Badge>
                  </div>
                ))}
              </Card>
            </Section>
          )}

          {ins && s.insight_narrative && (
            <Section title="Catchment insight" aside={
              <Badge tone={s.insight_narrative.source === "llm" ? "brand" : "neutral"}>
                {s.insight_narrative.source === "llm" ? <Bot className="h-3 w-3" /> : <FileText className="h-3 w-3" />}
                {s.insight_narrative.source === "llm" ? `AI · ${s.insight_narrative.model} · numbers verified` : "Rule-based summary"}
              </Badge>}>
              <Card className="p-4">
                <p className="font-medium text-slate-900">{s.insight_narrative.headline}</p>
                <p className="mt-1 text-sm text-slate-700">{s.insight_narrative.summary}</p>
                <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <Stat label="Households (est.)" value={ins.households_est.toLocaleString("en-IN")} note={`${ins.households_observed.toLocaleString("en-IN")} counted on ${ins.lanes_observed} lanes`} />
                  <Stat label="Residents vs model" value={ins.survey_vs_model === null ? "–" : `${ins.survey_vs_model >= 0 ? "+" : ""}${Math.round(ins.survey_vs_model * 100)}%`}
                    note={`${ins.population_est.toLocaleString("en-IN")} vs ${ins.modelled_population.toLocaleString("en-IN")} (Census 2011 model)`} />
                  <Stat label="Grocery shops" value={`${ins.kiranas_est}`} note={`counted ${ins.kiranas_observed}; OSM had ${ins.osm_competitors}`} />
                  <Stat label="Affluence index" value={ins.affluence_index === null ? "–" : `${ins.affluence_index}/100`} note="building condition + vehicles" />
                </div>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <Mix title="Housing" mix={ins.housing_mix} />
                  <Mix title="Footfall at survey time" mix={ins.footfall_mix} />
                </div>
                <ul className="mt-3 space-y-1 text-xs text-slate-500">
                  {s.insight_narrative.caveats.map((c, i) => <li key={i}>ⓘ {c}</li>)}
                  {ins.lanes_skipped > 0 && <li>ⓘ {ins.lanes_skipped} lanes skipped ({Object.entries(ins.skip_reasons).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(", ")}); counted as no homes.</li>}
                  {ins.captured_from && <li>ⓘ Observations from {ins.captured_from} to {ins.captured_to}{ins.source_studies.length > 1 ? `, across ${ins.source_studies.map((x) => x.code).join(", ")}` : ""}.</li>}
                </ul>
              </Card>
            </Section>
          )}
        </div>

        <div className="lg:sticky lg:top-4 lg:self-start">
          <Card className="overflow-hidden">
            <div className="flex gap-1 border-b border-slate-100 p-2 text-xs">
              {(["chunk", "status"] as const).map((k) => (
                <button key={k} onClick={() => setColorBy(k)} className={cn("rounded-md px-2 py-1 font-semibold", colorBy === k ? "bg-savo-purple-light text-savo-purple" : "text-slate-500")}>
                  Colour by {k}
                </button>
              ))}
            </div>
            <div className="h-[460px]">
              <MapView initialViewState={bounds ? { bounds, fitBoundsOptions: { padding: 30 } } : undefined}>
                {area && (
                  <Source id="catchment" type="geojson" data={area}>
                    <Layer id="catchment-fill" type="fill" paint={{ "fill-color": BRAND.purple, "fill-opacity": 0.05 }} />
                    <Layer id="catchment-line" type="line" paint={{ "line-color": BRAND.purple, "line-width": 2, "line-dasharray": [2, 2] }} />
                  </Source>
                )}
                {lanes.data && (
                  <Source id="study-lanes" type="geojson" data={lanes.data}>
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    <Layer id="study-lanes-line" type="line" layout={{ "line-cap": "round" }} paint={{ "line-color": colorExpr as any, "line-width": 3.5 }} />
                  </Source>
                )}
              </MapView>
            </div>
          </Card>
        </div>
      </div>

      {closeEarly && (
        <Modal title="Close the study early?" onClose={() => setCloseEarly(false)}>
          <p className="text-sm text-slate-600">Only {Math.round(p.closed_share * 100)}% of lanes are closed. Unsurveyed lanes will be extrapolated from the surveyed ones.</p>
          <textarea className="mt-3 min-h-20 w-full rounded-lg border border-slate-300 p-2 text-sm" placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
          <div className="mt-3 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setCloseEarly(false)}>Cancel</Button>
            <Button disabled={!reason.trim()} loading={act.complete.isPending} onClick={() => act.complete.mutate(reason, { onSuccess: () => setCloseEarly(false) })}>Close and roll up</Button>
          </div>
        </Modal>
      )}
      {resurveyOpen && (
        <Modal title="Ignore earlier surveys?" onClose={() => setResurveyOpen(false)}>
          <p className="text-sm text-slate-600">All lanes will be surveyed again. Use this when the area has changed (new buildings, demolitions) since the earlier study.</p>
          <textarea className="mt-3 min-h-20 w-full rounded-lg border border-slate-300 p-2 text-sm" placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
          {act.resurvey.error && <div className="mt-2"><ErrorNote error={act.resurvey.error} /></div>}
          <div className="mt-3 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setResurveyOpen(false)}>Cancel</Button>
            <Button disabled={reason.trim().length < 3} loading={act.resurvey.isPending} onClick={() => act.resurvey.mutate(reason, { onSuccess: () => setResurveyOpen(false) })}>
              <RotateCcw className="h-4 w-4" /> Resurvey all lanes
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-xl font-bold text-slate-900">{value}</div>
      {note && <div className="text-[11px] text-slate-500">{note}</div>}
    </div>
  );
}

function Mix({ title, mix }: { title: string; mix: Record<string, number> }) {
  const rows = Object.entries(mix).sort((a, b) => b[1] - a[1]);
  return (
    <div>
      <div className="mb-1 text-xs font-semibold uppercase text-slate-500">{title}</div>
      {rows.map(([k, v]) => (
        <div key={k} className="mb-1 flex items-center gap-2 text-xs">
          <span className="w-24 capitalize text-slate-600">{k.replace("_", " ")}</span>
          <div className="h-2 flex-1 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-savo-purple" style={{ width: `${v * 100}%` }} /></div>
          <span className="w-9 text-right tabular-nums text-slate-500">{Math.round(v * 100)}%</span>
        </div>
      ))}
    </div>
  );
}
