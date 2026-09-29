import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Layer, Marker, Source } from "react-map-gl/maplibre";
import type { FeatureCollection } from "geojson";
import {
  ArrowDownRight, ArrowLeft, ArrowUpRight, Bot, Building2, Clock, FileText, MessageSquarePlus, Pencil, RefreshCw, Store,
} from "lucide-react";
import { useProperty, usePropertyAction, type PropertyDetail } from "@/api/properties";
import { useAuth } from "@/stores/auth";
import { MapView } from "@/map/MapView";
import { BRAND, StoresLayer } from "@/map/layers";
import { Badge, Button, Card, ErrorNote, Spinner } from "@/components/ui";
import { FactChip, JobProgress, ScoreDial, Section } from "@/components/report";
import {
  CheckStatusIcon, FlagChips, Modal, RecPill, SeverityIcon, StageBadge, STAGE_LABEL, ago, inr,
} from "@/components/property";
import { cn } from "@/lib/cn";

function ring(lat: number, lon: number, r: number): FeatureCollection {
  const pts = Array.from({ length: 49 }, (_, i) => {
    const a = (i / 48) * 2 * Math.PI;
    return [lon + (r / (111320 * Math.cos((lat * Math.PI) / 180))) * Math.cos(a), lat + (r / 110540) * Math.sin(a)];
  });
  return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [pts] } }] };
}

export function PropertyPage() {
  const { id } = useParams();
  const user = useAuth((s) => s.user)!;
  const { data: p, isLoading, error } = useProperty(id);
  const actions = usePropertyAction(id!);
  const [pending, setPending] = useState<{ to: string; label: string; reason_required: boolean } | null>(null);
  const [reason, setReason] = useState("");
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("");
  const [photo, setPhoto] = useState<string | null>(null);
  const rings = useMemo(() => (p ? ring(p.lat, p.lon, 500) : null), [p?.lat, p?.lon]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading) return <div className="p-6"><Spinner label="Loading property…" /></div>;
  if (error || !p) return <div className="p-6"><ErrorNote error={error ?? new Error("Not found")} /></div>;

  const e = p.evaluation;
  const shown = e && e.score !== null ? e : p.last_completed_evaluation ?? e;
  const running = e && (e.status === "queued" || e.status === "running");
  const delta = p.previous_score !== null && p.latest_score !== null ? p.latest_score - p.previous_score : null;
  const facts = shown?.facts ?? {};
  const ctx = shown?.context;

  const doTransition = () => {
    if (!pending) return;
    actions.transition.mutate({ to: pending.to, reason: reason || undefined }, {
      onSuccess: () => { setPending(null); setReason(""); },
    });
  };

  return (
    <div className="mx-auto max-w-7xl p-4 md:p-6">
      <Link to={user.role === "BDM" ? "/bdm/pipeline" : "/bde/properties"} className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-savo-purple">
        <ArrowLeft className="h-4 w-4" /> {user.role === "BDM" ? "Pipeline" : "My properties"}
      </Link>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0 space-y-4">
          <Card className="p-4 md:p-5">
            <div className="flex flex-wrap items-start gap-4">
              {shown?.score !== null && shown?.score !== undefined && shown.recommendation ? (
                <div className="flex flex-col items-center gap-1">
                  <ScoreDial score={shown.score} grade={shown.score >= 75 ? "A" : shown.score >= 60 ? "B" : shown.score >= 45 ? "C" : "D"} size={104} />
                  {delta !== null && Math.abs(delta) >= 0.1 && (
                    <span className={cn("inline-flex items-center text-xs font-semibold", delta > 0 ? "text-emerald-700" : "text-red-700")}>
                      {delta > 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                      {delta > 0 ? "+" : ""}{delta.toFixed(1)} vs v{(shown.version ?? 1) - 1}
                    </span>
                  )}
                </div>
              ) : (
                <div className="flex h-24 w-24 items-center justify-center rounded-full bg-savo-purple-light"><Spinner label="" /></div>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span className="font-mono font-semibold text-savo-purple">{p.code}</span>
                  <StageBadge stage={p.stage} />
                  <RecPill rec={shown?.recommendation ?? null} />
                </div>
                <h1 className="mt-1 text-xl font-bold text-slate-900 md:text-2xl">{p.name}</h1>
                <p className="text-sm text-slate-500">
                  {p.landmark && `${p.landmark} · `}{p.pincode ?? ""} · by {p.created_by.name}, {ago(p.created_at)}
                  {p.scouting_task && <> · task: {p.scouting_task.title}</>}
                </p>
                {shown?.narrative && <p className="mt-2 font-medium text-slate-800">{shown.narrative.headline}</p>}
                <div className="mt-2"><FlagChips flags={p.flags} /></div>
              </div>
            </div>

            {running && e?.job && (
              <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p className="mb-2 text-xs font-semibold uppercase text-slate-500">Evaluation v{e.version} ({e.trigger})</p>
                <JobProgress steps={e.job.steps} status={e.status} />
              </div>
            )}

            <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
              {p.allowed_transitions.map((t) => (
                <Button key={t.to} variant={t.to === "REJECTED" ? "danger" : t.to === "ON_HOLD" ? "secondary" : "primary"}
                  onClick={() => { setPending(t); setReason(""); }}>
                  {t.label}
                </Button>
              ))}
              <Button variant="ghost" onClick={() => setNoteOpen(true)}><MessageSquarePlus className="h-4 w-4" /> Note</Button>
              {user.role === "BDM" && (
                <Button variant="ghost" loading={actions.reevaluate.isPending} onClick={() => actions.reevaluate.mutate()}>
                  <RefreshCw className="h-4 w-4" /> Re-evaluate
                </Button>
              )}
              {user.role === "BDE" && p.created_by.id === user.id && p.stage !== "APPROVED" && p.stage !== "REJECTED" && (
                <Link to={`/bde/edit/${p.id}`}><Button variant="ghost"><Pencil className="h-4 w-4" /> Edit details</Button></Link>
              )}
            </div>
            {actions.transition.error && <div className="mt-2"><ErrorNote error={actions.transition.error} /></div>}
          </Card>

          {p.studies.length > 0 && (
            <Card className="flex flex-wrap items-center gap-3 p-3 text-sm">
              <span className="font-semibold text-slate-700">Catchment studies:</span>
              {p.studies.map((st) => (
                <Link key={st.id} to={`${user.role === "SM" ? "/sm" : "/bdm"}/studies/${st.id}`} className="text-savo-purple hover:underline">
                  {st.code} · {st.status.toLowerCase().replace("_", " ")}
                  {st.reuse_mode !== "none" && ` · ${Math.round(st.reuse_coverage * 100)}% reused`}
                  {st.households_est ? ` · ~${st.households_est.toLocaleString("en-IN")} households` : ""}
                </Link>
              ))}
            </Card>
          )}

          {p.photos.length > 0 && (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {p.photos.map((ph) => (
                <button key={ph.id} onClick={() => setPhoto(ph.path)} className="relative h-28 w-40 shrink-0 overflow-hidden rounded-lg">
                  <img src={ph.path} alt={ph.kind} className="h-full w-full object-cover" />
                  <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1.5 text-[10px] text-white">{ph.kind}</span>
                </button>
              ))}
            </div>
          )}

          {shown?.insights && (
            <div className="grid gap-4 md:grid-cols-2">
              <Card className="p-4">
                <h2 className="mb-2 text-xs font-semibold uppercase text-emerald-700">In its favour</h2>
                <ul className="space-y-2 text-sm text-slate-700">
                  {shown.insights.map((i) => (
                    <li key={i.code} className="flex gap-2"><span className="text-emerald-600">+</span>
                      <span>{i.text}{i.fact_ids.map((f) => <FactChip key={f} id={f} fact={facts[f]} />)}</span></li>
                  ))}
                </ul>
              </Card>
              <Card className="p-4">
                <h2 className="mb-2 text-xs font-semibold uppercase text-red-700">Risks</h2>
                {shown.risks?.length ? (
                  <ul className="space-y-2 text-sm text-slate-700">
                    {shown.risks.map((r) => (
                      <li key={r.code} className="flex gap-2"><SeverityIcon severity={r.severity} />
                        <span>{r.text}{r.fact_ids.map((f) => <FactChip key={f} id={f} fact={facts[f]} />)}</span></li>
                    ))}
                  </ul>
                ) : <p className="text-sm text-slate-500">No material risks found.</p>}
              </Card>
            </div>
          )}

          {shown?.narrative && (
            <Card className="p-4">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase text-slate-500">Summary</h2>
                <Badge tone={shown.narrative_source === "llm" ? "brand" : "neutral"}>
                  {shown.narrative_source === "llm" ? <Bot className="h-3 w-3" /> : <FileText className="h-3 w-3" />}
                  {shown.narrative_source === "llm" ? `AI · ${shown.llm_model} · numbers verified` : "Rule-based summary"}
                </Badge>
              </div>
              <p className="text-sm text-slate-700">{shown.narrative.summary}</p>
              <p className="mt-2 text-sm font-medium text-savo-purple">Next step: {shown.narrative.next_step}</p>
            </Card>
          )}

          {shown?.checks && (
            <Section title={`Site checks · ${shown.site_score?.toFixed(0)}/100 (40% of score)`}>
              <Card className="divide-y divide-slate-100">
                {shown.checks.map((c) => (
                  <div key={c.key} className="flex items-start gap-3 px-3 py-2 text-sm">
                    <CheckStatusIcon status={c.status} />
                    <div className="min-w-0 flex-1">
                      <div className="flex justify-between gap-2">
                        <span className="font-medium text-slate-800">{c.label}</span>
                        <span className="tabular-nums text-slate-500">{c.score === null ? "–" : Math.round(c.score)}</span>
                      </div>
                      <div className="text-xs text-slate-500">{c.value} · {c.note}{c.key === "rent" && <Badge tone="highlight" className="ml-1">MOCK band</Badge>}</div>
                    </div>
                  </div>
                ))}
              </Card>
            </Section>
          )}

          {ctx?.location_subs && (
            <Section title={`Location · ${shown?.location_score?.toFixed(0)}/100 (60% of score, ~1 km around the pin)`}>
              <Card className="grid gap-x-6 gap-y-2 p-4 sm:grid-cols-2">
                {ctx.location_subs.map((s) => (
                  <div key={s.key} className="text-sm">
                    <div className="flex justify-between"><span className="text-slate-700">{s.label}</span><span className="font-semibold tabular-nums">{Math.round(s.score)}</span></div>
                    <div className="mt-1 h-1.5 rounded-full bg-slate-100"><div className="h-1.5 rounded-full bg-savo-purple" style={{ width: `${s.score}%` }} /></div>
                  </div>
                ))}
              </Card>
            </Section>
          )}

          <Section title="Captured details">
            <Card className="grid grid-cols-2 gap-x-6 gap-y-2 p-4 text-sm sm:grid-cols-3">
              <Detail label="Carpet area" value={p.carpet_sqft ? `${p.carpet_sqft.toLocaleString("en-IN")} sq ft` : "–"} />
              <Detail label="Rent / month" value={inr(p.rent_monthly)} />
              <Detail label="Floor" value={p.labels.floor[String(p.details.floor)] ?? "–"} />
              <Detail label="Frontage" value={p.details.frontage_ft ? `${p.details.frontage_ft} ft` : "–"} />
              <Detail label="Delivery" value={p.labels.delivery_access[String(p.details.delivery_access)] ?? "–"} />
              <Detail label="Visibility" value={p.labels.visibility[String(p.details.visibility)] ?? "–"} />
              <Detail label="Parking" value={`${p.details.parking_2w ?? 0} 2W · ${p.details.parking_4w ?? 0} car`} />
              <Detail label="Deposit" value={inr(p.details.deposit as number)} />
              <Detail label="Landlord" value={[p.details.landlord_name, p.details.landlord_phone].filter(Boolean).join(" · ") || "–"} />
            </Card>
          </Section>

          <Section title="History">
            <Card className="p-4">
              <ol className="space-y-3">
                {p.events.map((ev) => <TimelineItem key={ev.id} ev={ev} />)}
              </ol>
            </Card>
          </Section>
        </div>

        <div className="space-y-4 lg:sticky lg:top-4 lg:self-start">
          <Card className="overflow-hidden">
            <div className="h-80">
              <MapView initialViewState={{ latitude: p.lat, longitude: p.lon, zoom: 14.2 }}>
                {rings && (
                  <Source id="ring" type="geojson" data={rings}>
                    <Layer id="ring-line" type="line" paint={{ "line-color": BRAND.purple, "line-dasharray": [2, 2], "line-width": 1.5 }} />
                  </Source>
                )}
                <StoresLayer />
                {p.gps && (
                  <Marker longitude={p.gps.lon} latitude={p.gps.lat}>
                    <span className="block h-3 w-3 rounded-full border-2 border-white bg-blue-500" title="Phone location at capture" />
                  </Marker>
                )}
                <Marker longitude={p.lon} latitude={p.lat} anchor="bottom">
                  <Building2 className="h-8 w-8 fill-savo-yellow text-savo-purple drop-shadow" />
                </Marker>
              </MapView>
            </div>
            {ctx && (
              <div className="space-y-3 p-3 text-sm">
                <div>
                  <div className="text-xs font-semibold uppercase text-slate-500">Around the site</div>
                  <p className="text-slate-700">~{ctx.population_1km.toLocaleString("en-IN")} residents within 1 km <span className="text-xs text-slate-400">({ctx.population_source})</span></p>
                  {ctx.frontage_road && <p className="text-slate-700">Fronts {ctx.frontage_road.name ?? "an unnamed"} ({ctx.frontage_road.highway} road)</p>}
                  {ctx.rent_band && <p className="text-slate-700">Local band ₹{ctx.rent_band.min}–{ctx.rent_band.max}/sq ft <Badge tone="highlight">MOCK</Badge></p>}
                </div>
                <div>
                  <div className="flex items-center gap-1 text-xs font-semibold uppercase text-slate-500"><Store className="h-3 w-3" /> Competitors within 500 m ({ctx.competitors_500m.length})</div>
                  <ul className="mt-1 max-h-32 overflow-y-auto text-slate-700">
                    {ctx.competitors_500m.slice(0, 8).map((c, i) => (
                      <li key={i} className="flex justify-between gap-2">
                        <span className="truncate">{c.name} {c.tier === 3 && <Badge tone="danger">chain</Badge>}</span>
                        <span className="shrink-0 text-xs text-slate-400">{Math.round(c.dist_m)} m</span>
                      </li>
                    ))}
                    {!ctx.competitors_500m.length && <li className="text-slate-500">None mapped (verify on the ground)</li>}
                  </ul>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase text-slate-500">Nearest Savomart stores</div>
                  {ctx.nearest_stores.map((s) => (
                    <p key={s.code} className="flex justify-between text-slate-700"><span>{s.name}</span><span className="text-xs text-slate-400">{s.distance_km} km</span></p>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>

      {pending && (
        <Modal title={pending.label} onClose={() => setPending(null)}>
          <p className="text-sm text-slate-600">
            {STAGE_LABEL[p.stage]} → <span className="font-semibold">{pending.to === "RESUME" ? "previous stage" : STAGE_LABEL[pending.to as keyof typeof STAGE_LABEL]}</span>
          </p>
          <textarea
            className="mt-3 min-h-24 w-full rounded-lg border border-slate-300 p-2 text-sm focus:border-savo-purple focus:outline-none"
            placeholder={pending.reason_required ? "Reason (required, shown in the history)" : "Note for the team (optional)"}
            value={reason} onChange={(e) => setReason(e.target.value)}
          />
          {actions.transition.error && <div className="mt-2"><ErrorNote error={actions.transition.error} /></div>}
          <div className="mt-3 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setPending(null)}>Cancel</Button>
            <Button variant={pending.to === "REJECTED" ? "danger" : "primary"} loading={actions.transition.isPending}
              disabled={pending.reason_required && !reason.trim()} onClick={doTransition}>
              Confirm
            </Button>
          </div>
        </Modal>
      )}
      {noteOpen && (
        <Modal title="Add a note" onClose={() => setNoteOpen(false)}>
          <textarea className="min-h-24 w-full rounded-lg border border-slate-300 p-2 text-sm focus:border-savo-purple focus:outline-none"
            value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Landlord will reply by Friday" />
          <div className="mt-3 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setNoteOpen(false)}>Cancel</Button>
            <Button disabled={!note.trim()} loading={actions.note.isPending}
              onClick={() => actions.note.mutate(note, { onSuccess: () => { setNote(""); setNoteOpen(false); } })}>Add note</Button>
          </div>
        </Modal>
      )}
      {photo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4" onClick={() => setPhoto(null)}>
          <img src={photo} alt="" className="max-h-full max-w-full rounded-lg" />
        </div>
      )}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="font-medium text-slate-800">{value}</div>
    </div>
  );
}

function TimelineItem({ ev }: { ev: PropertyDetail["events"][number] }) {
  const when = new Date(ev.at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" });
  const who = ev.actor ?? "System";
  let text: string;
  if (ev.kind === "stage") {
    text = ev.from_stage ? `moved ${STAGE_LABEL[ev.from_stage]} → ${STAGE_LABEL[ev.to_stage!]}` : "onboarded the property";
  } else if (ev.kind === "evaluation") {
    const d = ev.data as { version: number; score: number; recommendation: string; previous_score: number | null; trigger: string };
    text = `evaluation v${d.version} (${d.trigger}): ${d.score?.toFixed(1)}${d.previous_score !== null ? ` (was ${d.previous_score.toFixed(1)})` : ""} → ${d.recommendation}`;
  } else if (ev.kind === "edit") {
    text = `edited ${((ev.data as { changed?: string[] })?.changed ?? []).join(", ").replaceAll("_", " ") || "details"}`;
  } else {
    text = "added a note";
  }
  return (
    <li className="flex gap-3 text-sm">
      <Clock className="mt-0.5 h-4 w-4 shrink-0 text-slate-300" />
      <div>
        <span className="font-medium text-slate-800">{who}</span> <span className="text-slate-600">{text}</span>
        {ev.reason && <p className="mt-0.5 rounded bg-slate-50 px-2 py-1 text-slate-700">“{ev.reason}”</p>}
        <div className="text-xs text-slate-400">{when}</div>
      </div>
    </li>
  );
}
