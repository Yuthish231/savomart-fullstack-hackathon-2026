import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import type { FeatureCollection } from "geojson";
import { Layer, Marker, Source } from "react-map-gl/maplibre";
import { ArrowLeft, Bot, Database, FileText, RotateCcw, Store, TrainFront } from "lucide-react";
import { isTerminal, useReport, useRetryReport, type Report } from "@/api/areas";
import { MapView } from "@/map/MapView";
import { BRAND, StoresLayer } from "@/map/layers";
import { Badge, Button, Card, ErrorNote, Spinner } from "@/components/ui";
import { ConfidenceBadge, FactChip, JobProgress, ScoreDial, Section, SubScoreCard } from "@/components/report";

const fmtDate = (s: string) =>
  new Date(s).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" });

function bboxOf(geom: Report["area_geometry"]): [[number, number], [number, number]] {
  const xs: number[] = [];
  const ys: number[] = [];
  const walk = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number") {
      xs.push(c[0] as number);
      ys.push(c[1] as number);
    } else if (Array.isArray(c)) c.forEach(walk);
  };
  walk((geom as { coordinates: unknown }).coordinates);
  return [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]];
}

export function ReportPage() {
  const { id } = useParams();
  const { data: r, error, isLoading } = useReport(id);
  const retry = useRetryReport(id!);

  const areaFc = useMemo<FeatureCollection | null>(
    () => (r ? { type: "FeatureCollection", features: [{ type: "Feature", geometry: r.area_geometry, properties: {} }] } : null),
    [r?.id], // geometry never changes for a report
  );

  if (isLoading) return <div className="p-6"><Spinner label="Loading report…" /></div>;
  if (error || !r) return <div className="p-6"><ErrorNote error={error ?? new Error("Report not found")} /></div>;

  const running = !isTerminal(r.status);
  const n = r.narrative;
  const facts = r.facts ?? {};
  const m = r.metrics;

  return (
    <div className="mx-auto max-w-7xl p-4 md:p-6">
      <Link to="/bdm/reports" className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-savo-purple">
        <ArrowLeft className="h-4 w-4" /> All reports
      </Link>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="min-w-0">
          <Card className="p-4 md:p-5">
            <div className="flex flex-wrap items-start gap-4">
              {r.overall_score !== null && r.grade ? (
                <ScoreDial score={r.overall_score} grade={r.grade} />
              ) : (
                <div className="flex h-28 w-28 items-center justify-center rounded-full bg-savo-purple-light">
                  <Spinner label="" />
                </div>
              )}
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold uppercase tracking-wide text-savo-purple">Area Fitness Report</div>
                <h1 className="text-xl font-bold text-slate-900 md:text-2xl">{r.area_name}</h1>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>{r.area_km2.toFixed(1)} km² · {r.selection_type}</span>
                  <span>· run {fmtDate(r.created_at)} by {r.created_by_name}</span>
                  <ConfidenceBadge level={r.confidence} />
                  <Badge>model {r.scoring_version}</Badge>
                </div>
                {n && <p className="mt-3 font-medium text-slate-800">{n.headline}</p>}
              </div>
            </div>

            {(running || r.status === "failed" || r.status === "partial") && r.job && (
              <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
                <JobProgress steps={r.job.steps} status={r.status} />
                {(r.status === "failed" || r.status === "partial") && (
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <span className="text-sm text-slate-600">
                      {r.status === "partial" ? r.error : "The analysis stopped part-way. Finished steps are kept."}
                    </span>
                    <Button variant="secondary" loading={retry.isPending} onClick={() => retry.mutate()}>
                      <RotateCcw className="h-4 w-4" /> Retry from failed step
                    </Button>
                  </div>
                )}
              </div>
            )}
          </Card>

          {n && (
            <Section
              title="Assessment"
              aside={
                <Badge tone={r.narrative_source === "llm" ? "brand" : "neutral"}>
                  {r.narrative_source === "llm" ? <Bot className="h-3 w-3" /> : <FileText className="h-3 w-3" />}
                  {r.narrative_source === "llm" ? `AI summary · ${r.llm_model} · numbers verified` : "Rule-based summary"}
                </Badge>
              }
            >
              <Card className="p-4">
                <p className="text-slate-700">{n.summary}</p>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <div>
                    <h3 className="text-xs font-semibold uppercase text-emerald-700">Why it fits</h3>
                    <ul className="mt-1 space-y-1.5 text-sm text-slate-700">
                      {n.reasons.map((x, i) => (
                        <li key={i}>• {x.text}{x.fact_ids.map((f) => <FactChip key={f} id={f} fact={facts[f]} />)}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h3 className="text-xs font-semibold uppercase text-amber-700">Risks</h3>
                    <ul className="mt-1 space-y-1.5 text-sm text-slate-700">
                      {n.risks.map((x, i) => (
                        <li key={i}>• {x.text}{x.fact_ids.map((f) => <FactChip key={f} id={f} fact={facts[f]} />)}</li>
                      ))}
                    </ul>
                  </div>
                </div>
                {n.scout_first.length > 0 && (
                  <div className="mt-4 rounded-lg bg-savo-purple p-3 text-white">
                    <h3 className="text-xs font-semibold uppercase text-savo-yellow">Scout here first</h3>
                    <ul className="mt-1 space-y-1 text-sm">
                      {n.scout_first.map((x) => <li key={x.hotspot_id}>• {x.text}</li>)}
                    </ul>
                  </div>
                )}
                {n.caveats.length > 0 && (
                  <ul className="mt-3 space-y-1 text-xs text-slate-500">
                    {n.caveats.map((c, i) => <li key={i}>ⓘ {c}</li>)}
                  </ul>
                )}
              </Card>
            </Section>
          )}

          {r.sub_scores && (
            <Section title="How the score was reached">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {r.sub_scores.map((s) => <SubScoreCard key={s.key} s={s} />)}
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Score = Σ weight × sub-score. Percentiles compare this area with every inhabited ~2 km² neighbourhood in the
                Chennai Metropolitan Area.
              </p>
            </Section>
          )}

          {m && (
            <Section title="What the area is like">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <Stat label="Estimated residents" value={m.population.toLocaleString("en-IN")} note="Census 2011 baseline" />
                <Stat label="Residential buildings" value={m.residential_buildings.toLocaleString("en-IN")} note={`${m.buildings.toLocaleString("en-IN")} buildings mapped`} />
                <Stat
                  label="Grocery competitors"
                  value={String(m.competitors.kirana_convenience + m.competitors.supermarket + m.competitors.organised_chain)}
                  note={`${m.competitors.organised_chain} chain · ${m.competitors.supermarket} supermkt · ${m.competitors.kirana_convenience} kirana; ${m.competitors_in_ring} more within ~500 m`}
                />
                <Stat label="Nearest Savomart" value={`${m.nearest_store.distance_km} km`} note={m.nearest_store.name} />
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <Card className="p-3 text-sm">
                  <div className="mb-1 flex items-center gap-1.5 font-semibold text-slate-700"><Store className="h-4 w-4" /> Organised chains nearby</div>
                  {m.organised_chains_nearby.length ? (
                    <p className="text-slate-600">{m.organised_chains_nearby.map((c) => `${c.name} (${c.n})`).join(", ")}</p>
                  ) : <p className="text-slate-500">None mapped in or around the area.</p>}
                  <div className="mt-2 text-xs text-slate-500">
                    Savomart within 3 km:{" "}
                    {m.savomart_stores_within_3km.length
                      ? m.savomart_stores_within_3km.map((s) => `${s.name} (${(s.dist_m / 1000).toFixed(1)} km)`).join(", ")
                      : "none"}
                  </div>
                </Card>
                <Card className="p-3 text-sm">
                  <div className="mb-1 flex items-center gap-1.5 font-semibold text-slate-700"><TrainFront className="h-4 w-4" /> Amenities & access</div>
                  <p className="text-slate-600">
                    {Object.entries(m.poi_by_category)
                      .filter(([k]) => k !== "grocery" && k !== "own_store")
                      .sort((a, b) => b[1] - a[1])
                      .map(([k, v]) => `${v} ${k}`)
                      .join(" · ") || "Few amenities mapped."}
                  </p>
                  <p className="mt-2 text-xs text-slate-500">
                    Rail/metro: {m.rail_metro_stations.join(", ") || "none in area"} · roads {m.road_major_km} km arterial, {m.road_minor_km} km local
                  </p>
                </Card>
              </div>
            </Section>
          )}

          {r.data_sources && (
            <Section title="Data used">
              <Card className="p-3">
                <ul className="grid gap-1 text-xs text-slate-600 sm:grid-cols-2">
                  {r.data_sources.map((d) => (
                    <li key={d.key} className="flex items-center gap-1.5">
                      <Database className="h-3 w-3 text-slate-400" />
                      {d.name}
                      <span className="text-slate-400">· as of {d.as_of ?? "n/a"}</span>
                      {d.is_mock && <Badge tone="highlight">MOCK</Badge>}
                    </li>
                  ))}
                </ul>
                {r.completed_at && <p className="mt-2 text-[11px] text-slate-400">Snapshot taken {fmtDate(r.completed_at)}. Re-running later may give different numbers if data is refreshed.</p>}
              </Card>
            </Section>
          )}
        </div>

        <div className="lg:sticky lg:top-4 lg:self-start">
          <Card className="overflow-hidden">
            <div className="h-80 lg:h-[440px]">
              <MapView initialViewState={{ bounds: bboxOf(r.area_geometry), fitBoundsOptions: { padding: 40 } }}>
                {areaFc && (
                  <Source id="area" type="geojson" data={areaFc}>
                    <Layer id="area-fill" type="fill" paint={{ "fill-color": BRAND.purple, "fill-opacity": 0.08 }} />
                    <Layer id="area-line" type="line" paint={{ "line-color": BRAND.purple, "line-width": 2.5 }} />
                  </Source>
                )}
                <StoresLayer />
                {r.hotspots?.map((h) => (
                  <Marker key={h.id} longitude={h.lon} latitude={h.lat}>
                    <span className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-savo-purple bg-savo-yellow text-xs font-bold text-savo-purple shadow">
                      {h.rank}
                    </span>
                  </Marker>
                ))}
              </MapView>
            </div>
            {r.hotspots && r.hotspots.length > 0 && (
              <div className="border-t border-slate-100 p-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Scouting hotspots</h3>
                <ol className="mt-2 space-y-2">
                  {r.hotspots.map((h) => (
                    <li key={h.id} className="flex gap-2 text-sm">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-savo-yellow text-xs font-bold text-savo-purple ring-2 ring-savo-purple">
                        {h.rank}
                      </span>
                      <span>
                        <span className="font-medium">{h.near_road ?? "Unnamed streets"}</span>{" "}
                        <span className="text-slate-500">· score {Math.round(h.score)} · {h.nearest_store_km} km to Savomart</span>
                        <span className="block text-xs text-slate-500">Strong on {h.strengths.map((s) => s.label.toLowerCase()).join(" and ")}</span>
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card className="p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-xl font-bold text-slate-900">{value}</div>
      {note && <div className="text-[11px] text-slate-500">{note}</div>}
    </Card>
  );
}
