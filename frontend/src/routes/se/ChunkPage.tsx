import { useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useLiveQuery } from "dexie-react-hooks";
import { Layer, Source, type MapLayerMouseEvent, type MapRef } from "react-map-gl/maplibre";
import type { FeatureCollection, LineString } from "geojson";
import { ArrowLeft, Ban, Check, ChevronRight, CloudUpload, Minus, Plus, WifiOff, X } from "lucide-react";
import { api } from "@/api/client";
import type { ChunkDetail, LaneData, LaneProps } from "@/api/studies";
import { fieldDb, type LocalSurvey } from "@/offline/db";
import { saveLocal, syncNow } from "@/offline/sync";
import { MapView } from "@/map/MapView";
import { BRAND } from "@/map/layers";
import { Button, ErrorNote, Spinner } from "@/components/ui";
import { cn } from "@/lib/cn";

const STATUS_COLOR: Record<string, string> = {
  todo: "#94a3b8", draft: "#f59e0b", done: "#10b981", skipped: "#475569", reused: "#a78bfa",
};

/** Network first; fall back to the copy saved on this phone so the chunk opens with no signal. */
function useChunk(id: string) {
  return useQuery({
    queryKey: ["chunk", id],
    queryFn: async () => {
      try {
        const d = await api<ChunkDetail>(`/chunks/${id}`);
        await fieldDb.chunks.put({ chunk_id: id, payload: d, cached_at: new Date().toISOString() });
        return { data: d, offline: false };
      } catch (e) {
        const c = await fieldDb.chunks.get(id);
        if (c) return { data: c.payload, offline: true };
        throw e;
      }
    },
    retry: false,
  });
}

export function ChunkPage() {
  const { id } = useParams();
  const q = useChunk(id!);
  const local = useLiveQuery(() => fieldDb.surveys.where("chunk_id").equals(id!).toArray(), [id], []);
  const [selected, setSelected] = useState<string | null>(null);
  const mapRef = useRef<MapRef>(null);

  const d = q.data?.data;
  const localByLane = useMemo(() => new Map((local ?? []).map((s) => [s.lane_id, s])), [local]);

  const status = (p: LaneProps): string => {
    const l = localByLane.get(p.id);
    if (l) return l.status === "submitted" ? "done" : l.status === "skipped" ? "skipped" : "draft";
    return p.status;
  };

  const fc = useMemo<FeatureCollection<LineString, LaneProps & { st: string; sel: boolean }> | null>(() => {
    if (!d) return null;
    return {
      type: "FeatureCollection",
      features: d.lanes.features.map((f) => ({ ...f, properties: { ...f.properties, st: status(f.properties), sel: f.properties.id === selected } })),
    };
  }, [d, localByLane, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  const bounds = useMemo(() => {
    if (!d?.lanes.features.length) return undefined;
    const xs: number[] = [], ys: number[] = [];
    d.lanes.features.forEach((f) => f.geometry.coordinates.forEach(([x, y]) => { xs.push(x); ys.push(y); }));
    return [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]] as [[number, number], [number, number]];
  }, [d]);

  if (q.isLoading) return <div className="p-6"><Spinner label="Loading lanes…" /></div>;
  if (q.error || !d) return <div className="p-6"><ErrorNote error={q.error ?? new Error("Chunk not found")} /></div>;

  const lanes = d.lanes.features.map((f) => f.properties);
  const closed = lanes.filter((l) => ["done", "skipped"].includes(status(l))).length;
  const unsynced = (local ?? []).filter((s) => !s.synced).length;
  const sel = lanes.find((l) => l.id === selected) ?? null;

  const nextLane = (from: string) => {
    const cur = d.lanes.features.find((f) => f.properties.id === from);
    const [cx, cy] = cur?.geometry.coordinates[0] ?? [0, 0];
    const todo = d.lanes.features.filter((f) => f.properties.id !== from && ["todo", "draft"].includes(status(f.properties)));
    todo.sort((a, b) => {
      const [ax, ay] = a.geometry.coordinates[0], [bx, by] = b.geometry.coordinates[0];
      return (ax - cx) ** 2 + (ay - cy) ** 2 - ((bx - cx) ** 2 + (by - cy) ** 2);
    });
    const n = todo[0];
    setSelected(n ? n.properties.id : null);
    if (n) mapRef.current?.easeTo({ center: n.geometry.coordinates[0] as [number, number], zoom: 17 });
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col pb-4">
      <div className="border-b border-slate-200 bg-white px-4 py-3">
        <Link to="/se/assignments" className="inline-flex items-center gap-1 text-xs text-slate-500"><ArrowLeft className="h-3 w-3" /> Assignments</Link>
        <div className="mt-1 flex items-center justify-between gap-2">
          <h1 className="font-bold text-slate-900">Chunk {d.chunk.label} · <span className="text-savo-purple">{d.study.code}</span></h1>
          <span className="text-sm font-semibold text-slate-700">{closed}/{lanes.length}</span>
        </div>
        <p className="truncate text-xs text-slate-500">{d.study.title}</p>
        <div className="mt-2 h-1.5 rounded-full bg-slate-100"><div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${(100 * closed) / lanes.length}%` }} /></div>
        {q.data?.offline && (
          <p className="mt-2 flex items-center gap-1 text-xs text-amber-800"><WifiOff className="h-3 w-3" /> Offline copy from this phone. Your entries are saved and will sync later.</p>
        )}
        {unsynced > 0 && !q.data?.offline && (
          <button onClick={() => void syncNow()} className="mt-2 flex items-center gap-1 text-xs font-semibold text-savo-purple">
            <CloudUpload className="h-3 w-3" /> {unsynced} lane{unsynced > 1 ? "s" : ""} waiting to sync · sync now
          </button>
        )}
      </div>

      <div className="h-72 border-b border-slate-200">
        <MapView ref={mapRef} initialViewState={bounds ? { bounds, fitBoundsOptions: { padding: 30 } } : undefined}
          interactiveLayerIds={["lanes-hit"]}
          onClick={(e: MapLayerMouseEvent) => { const f = e.features?.[0]; if (f) setSelected(String(f.properties?.id)); }}>
          {fc && (
            <Source id="lanes" type="geojson" data={fc}>
              <Layer id="lanes-hit" type="line" paint={{ "line-color": "#000", "line-opacity": 0, "line-width": 18 }} />
              <Layer id="lanes-sel" type="line" filter={["==", ["get", "sel"], true]} paint={{ "line-color": BRAND.yellow, "line-width": 10 }} />
              <Layer id="lanes-line" type="line" layout={{ "line-cap": "round" }}
                paint={{
                  "line-color": ["match", ["get", "st"], "draft", STATUS_COLOR.draft, "done", STATUS_COLOR.done,
                    "skipped", STATUS_COLOR.skipped, "reused", STATUS_COLOR.reused, STATUS_COLOR.todo],
                  "line-width": 4,
                }} />
            </Source>
          )}
        </MapView>
      </div>
      <div className="flex flex-wrap gap-3 px-4 py-2 text-[11px] text-slate-500">
        {Object.entries({ todo: "To do", draft: "Draft", done: "Done", skipped: "Skipped" }).map(([k, v]) => (
          <span key={k} className="flex items-center gap-1"><span className="inline-block h-1 w-4 rounded" style={{ background: STATUS_COLOR[k] }} />{v}</span>
        ))}
      </div>

      <div className="space-y-1 px-2">
        {lanes.map((l) => {
          const st = status(l);
          const ls = localByLane.get(l.id);
          return (
            <button key={l.id} onClick={() => setSelected(l.id)}
              className={cn("flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm hover:bg-slate-50", selected === l.id && "bg-savo-purple-light")}>
              <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: STATUS_COLOR[st] }} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-slate-800">{l.name ?? "Unnamed lane"}</span>
                <span className="text-xs text-slate-500">{Math.round(l.length_m)} m · {l.highway.replace("_", " ")}</span>
              </span>
              {ls && !ls.synced && <CloudUpload className="h-4 w-4 text-amber-500" aria-label="waiting to sync" />}
              {ls?.conflict && <span className="text-[10px] font-semibold text-red-600">conflict</span>}
              <ChevronRight className="h-4 w-4 text-slate-300" />
            </button>
          );
        })}
      </div>

      {sel && (
        <LaneForm key={sel.id} lane={sel} studyId={d.study.id} chunkId={d.chunk.id} local={localByLane.get(sel.id)}
          onClose={() => setSelected(null)} onNext={() => nextLane(sel.id)} />
      )}
    </div>
  );
}

const Q = <T extends string>(v: T, label: string) => ({ v, label });

function ChipRow<T extends string>({ label, value, options, onChange }: { label: string; value?: T; options: { v: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div>
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => (
          <button type="button" key={o.v} onClick={() => onChange(o.v)} aria-pressed={value === o.v}
            className={cn("min-h-10 rounded-full border px-3 text-sm font-medium", value === o.v ? "border-savo-purple bg-savo-purple text-white" : "border-slate-300 bg-white text-slate-700")}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function LaneForm({ lane, studyId, chunkId, local, onClose, onNext }: {
  lane: LaneProps; studyId: string; chunkId: string; local?: LocalSurvey; onClose: () => void; onNext: () => void;
}) {
  const server = lane.survey;
  const [uuid] = useState(() => local?.client_uuid ?? server?.client_uuid ?? crypto.randomUUID());
  const [data, setData] = useState<LaneData>(() => local?.data ?? server?.data ?? {});
  // Latest values, independent of render timing, so rapid taps never overwrite each other.
  const latest = useRef<LaneData>(data);
  const [skip, setSkip] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const baseVersion = local?.base_version ?? server?.version ?? null;

  const persist = async (next: LaneData, status: LocalSurvey["status"]) => {
    await saveLocal({ client_uuid: uuid, study_id: studyId, chunk_id: chunkId, lane_id: lane.id, status, data: next,
      captured_at: new Date().toISOString(), base_version: baseVersion });
  };
  const set = (patch: Partial<LaneData>) => {
    latest.current = { ...latest.current, ...patch };
    setData(latest.current);
    void persist(latest.current, "draft"); // every tap is saved on the phone immediately
  };
  const complete = !!data.housing_type && !!data.dwellings_bucket && data.kiranas !== undefined;

  const submit = async () => {
    if (!complete) return setError("Housing type, homes and kirana count are needed to finish the lane.");
    await persist(latest.current, "submitted");
    void syncNow();
    onNext();
  };
  const doSkip = async (reason: NonNullable<LaneData["skip_reason"]>) => {
    const next = { ...latest.current, skip_reason: reason };
    await persist(next, "skipped");
    void syncNow();
    onNext();
  };


  return (
    <div className="fixed inset-x-0 bottom-0 z-40 max-h-[85vh] overflow-y-auto rounded-t-2xl border-t border-slate-200 bg-white p-4 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-2xl md:left-52">
      <div className="mx-auto max-w-2xl space-y-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="font-bold text-slate-900">{lane.name ?? "Unnamed lane"}</div>
            <div className="text-xs text-slate-500">{Math.round(lane.length_m)} m · saved on this phone as you tap</div>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-slate-400 hover:bg-slate-100"><X className="h-5 w-5" /></button>
        </div>

        {skip ? (
          <ChipRow label="Why skip this lane?" value={data.skip_reason} onChange={(v) => void doSkip(v)} options={[
            Q("gated", "Gated / no entry"), Q("not_residential", "Not residential"), Q("under_construction", "Under construction"),
            Q("inaccessible", "Can't reach"), Q("other", "Other")]} />
        ) : (
          <>
            <ChipRow label="Mostly" value={data.housing_type} onChange={(v) => set({ housing_type: v })} options={[
              Q("independent", "Houses"), Q("apartments", "Apartments"), Q("mixed", "Mixed"), Q("informal", "Informal"), Q("commercial", "Commercial")]} />
            <ChipRow label="Homes on this lane" value={data.dwellings_bucket} onChange={(v) => set({ dwellings_bucket: v })} options={[
              Q("0-10", "0–10"), Q("11-25", "11–25"), Q("26-50", "26–50"), Q("51-100", "51–100"), Q("100+", "100+")]} />
            <div>
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Kiranas / grocery shops</div>
              <div className="flex items-center gap-3">
                <Stepper onClick={() => set({ kiranas: Math.max(0, (data.kiranas ?? 0) - 1) })}><Minus className="h-5 w-5" /></Stepper>
                <span className="w-10 text-center text-2xl font-bold tabular-nums">{data.kiranas ?? "–"}</span>
                <Stepper onClick={() => set({ kiranas: (data.kiranas ?? -1) + 1 })}><Plus className="h-5 w-5" /></Stepper>
                <label className="ml-2 flex items-center gap-2 text-sm">
                  <input type="checkbox" className="h-5 w-5 accent-savo-purple" checked={!!data.organised_present}
                    onChange={(e) => set({ organised_present: e.target.checked })} /> Chain store here
                </label>
              </div>
            </div>
            <ChipRow label="Buildings look" value={data.condition} onChange={(v) => set({ condition: v })} options={[
              Q("new", "New"), Q("maintained", "Kept up"), Q("old", "Old"), Q("dilapidated", "Run-down")]} />
            <ChipRow label="Parked vehicles" value={data.vehicles} onChange={(v) => set({ vehicles: v })} options={[
              Q("mostly_2w", "Mostly 2-wheelers"), Q("mixed", "Mixed"), Q("many_cars", "Many cars")]} />
            <ChipRow label="People around now" value={data.footfall} onChange={(v) => set({ footfall: v })} options={[
              Q("low", "Quiet"), Q("medium", "Some"), Q("high", "Busy")]} />
            <ChipRow label="Delivery vehicle can enter" value={data.delivery_access} onChange={(v) => set({ delivery_access: v })} options={[
              Q("truck", "Truck"), Q("van", "Van"), Q("two_wheeler", "2-wheeler only"), Q("none", "No")]} />
            <input className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm focus:border-savo-purple focus:outline-none"
              placeholder="Shop names or notes (optional)" value={data.notes ?? ""} onChange={(e) => set({ notes: e.target.value })} />
          </>
        )}
        {error && <p className="text-sm text-red-700">{error}</p>}
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setSkip((s) => !s)}><Ban className="h-4 w-4" /> {skip ? "Back" : "Skip lane"}</Button>
          {!skip && <Button className="flex-1" onClick={() => void submit()} disabled={!complete}><Check className="h-4 w-4" /> Done · next lane</Button>}
        </div>
      </div>
    </div>
  );
}

function Stepper({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="flex h-11 w-11 items-center justify-center rounded-full border border-slate-300 bg-white text-slate-700 active:bg-slate-100">
      {children}
    </button>
  );
}
