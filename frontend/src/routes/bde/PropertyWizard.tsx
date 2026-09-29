import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Layer, Marker, Source, type MapRef } from "react-map-gl/maplibre";
import type { FeatureCollection } from "geojson";
import { Camera, Check, ChevronLeft, ChevronRight, Crosshair, ImagePlus, Loader2, LocateFixed, MapPin, Trash2 } from "lucide-react";
import {
  uploadPhoto, usePrecheck, useProperty, useSaveProperty, useTasks,
  type PrecheckResult, type PropertyForm,
} from "@/api/properties";
import { MapView } from "@/map/MapView";
import { BRAND } from "@/map/layers";
import { Badge, Button, Card, ErrorNote } from "@/components/ui";
import { compressImage } from "@/lib/image";
import { useDrafts, type Draft } from "@/stores/draft";
import { cn } from "@/lib/cn";

const STEPS = ["Pin", "Details", "Photos"] as const;
const PHOTO_SLOTS = [
  { kind: "front", label: "Shop front" },
  { kind: "interior", label: "Inside" },
  { kind: "street", label: "Street view" },
] as const;

type Photo = { kind: string; blob: Blob; url: string };

function Chips<T extends string>({ value, options, onChange }: {
  value: T | null | undefined; options: { v: T; label: string }[]; onChange: (v: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          type="button"
          key={o.v}
          onClick={() => onChange(o.v)}
          aria-pressed={value === o.v}
          className={cn(
            "min-h-10 rounded-full border px-3 text-sm font-medium",
            value === o.v ? "border-savo-purple bg-savo-purple text-white" : "border-slate-300 bg-white text-slate-700",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Field({ label, hint, required, children }: { label: string; hint?: ReactNode; required?: boolean; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-semibold text-slate-700">
        {label} {required && <span className="text-red-600">*</span>}
      </span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

const inputCls = "w-full min-h-11 rounded-lg border border-slate-300 px-3 text-base focus:border-savo-purple focus:outline-none";

function NumberInput({ value, onChange, placeholder, suffix }: {
  value: number | null | undefined; onChange: (v: number | null) => void; placeholder?: string; suffix?: string;
}) {
  return (
    <div className="relative">
      <input
        inputMode="decimal"
        className={inputCls}
        value={value ?? ""}
        placeholder={placeholder}
        onChange={(e) => {
          const t = e.target.value.replace(/[^0-9.]/g, "");
          onChange(t === "" ? null : Number(t));
        }}
      />
      {suffix && <span className="pointer-events-none absolute right-3 top-3 text-sm text-slate-400">{suffix}</span>}
    </div>
  );
}

function circle(lat: number, lon: number, r: number): FeatureCollection {
  const pts = Array.from({ length: 41 }, (_, i) => {
    const a = (i / 40) * 2 * Math.PI;
    return [lon + (r / (111320 * Math.cos((lat * Math.PI) / 180))) * Math.cos(a), lat + (r / 110540) * Math.sin(a)];
  });
  return { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [pts] } }] };
}

export function PropertyWizard() {
  const { id: editId } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const key = editId ?? "new";
  const { drafts, save, clear } = useDrafts();
  const existing = useProperty(editId);
  const tasks = useTasks();
  const taskId = params.get("task") ?? drafts[key]?.scouting_task_id ?? null;
  const task = tasks.data?.find((t) => t.id === taskId);

  const [d, setD] = useState<Draft>(() => drafts[key] ?? { property_type: "shop", floor: "ground", step: 0 });
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [gpsState, setGpsState] = useState<"idle" | "locating" | "ok" | "denied">("idle");
  const [submitState, setSubmitState] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const precheck = usePrecheck();
  const saveProp = useSaveProperty(editId);
  const mapRef = useRef<MapRef>(null);
  const step = d.step ?? 0;

  const set = (patch: Draft) => setD((cur) => ({ ...cur, ...patch }));
  useEffect(() => save(key, d), [d]); // eslint-disable-line react-hooks/exhaustive-deps

  // Edit mode: prefill once from the saved property (unless a newer local draft exists).
  useEffect(() => {
    const p = existing.data;
    if (!p || drafts[key]?.name) return;
    set({
      name: p.name, lat: p.lat, lon: p.lon, gps: p.gps ?? null, address: p.address ?? "", landmark: p.landmark ?? "",
      carpet_sqft: p.carpet_sqft ?? undefined, rent_monthly: p.rent_monthly, ...(p.details as Partial<PropertyForm>),
    });
  }, [existing.data]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (taskId && !d.scouting_task_id) set({ scouting_task_id: taskId });
  }, [taskId]); // eslint-disable-line react-hooks/exhaustive-deps

  const locate = () => {
    if (!("geolocation" in navigator)) return setGpsState("denied");
    setGpsState("locating");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const gps = { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: Math.round(pos.coords.accuracy) };
        setGpsState("ok");
        setD((cur) => ({ ...cur, gps, lat: cur.lat ?? gps.lat, lon: cur.lon ?? gps.lon }));
        mapRef.current?.flyTo({ center: [gps.lon, gps.lat], zoom: 17 });
      },
      () => setGpsState("denied"),
      { enableHighAccuracy: true, timeout: 12_000, maximumAge: 30_000 },
    );
  };
  useEffect(() => {
    if (!editId && !d.gps) locate();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Without GPS, start the pin at the scouting task's hotspot.
  useEffect(() => {
    if (task && d.lat === undefined) set({ lat: task.lat, lon: task.lon });
  }, [task]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-check location, pincode, rent band and duplicates whenever the pin or name settles.
  const [check, setCheck] = useState<PrecheckResult | null>(null);
  useEffect(() => {
    if (d.lat === undefined || d.lon === undefined) return;
    const t = setTimeout(() => {
      precheck.mutate({ lat: d.lat!, lon: d.lon!, name: d.name ?? "", landmark: d.landmark },
        { onSuccess: (r) => setCheck({ ...r, duplicates: r.duplicates.filter((x) => x.id !== editId) }) });
    }, 600);
    return () => clearTimeout(t);
  }, [d.lat, d.lon, d.name, d.landmark]); // eslint-disable-line react-hooks/exhaustive-deps

  const pinGpsGap = useMemo(() => {
    if (!d.gps || d.lat === undefined || d.lon === undefined) return null;
    const dx = (d.lon - d.gps.lon) * 111320 * Math.cos((d.lat * Math.PI) / 180);
    const dy = (d.lat - d.gps.lat) * 110540;
    return Math.round(Math.hypot(dx, dy));
  }, [d.lat, d.lon, d.gps]);

  const stepValid = [
    d.lat !== undefined && check?.in_region !== false && (!check?.duplicates.length || !!d.confirmed_not_duplicate),
    !!d.name && d.name.trim().length >= 3 && !!d.floor && !!d.carpet_sqft && d.carpet_sqft >= 50,
    true,
  ];

  const onPhoto = async (kind: string, file?: File) => {
    if (!file) return;
    try {
      const blob = await compressImage(file);
      setPhotos((cur) => [...cur.filter((p) => p.kind !== kind || kind === "other"), { kind, blob, url: URL.createObjectURL(blob) }]);
    } catch (e) {
      setError(e);
    }
  };

  const submit = async () => {
    setError(null);
    const { step: _s, savedAt: _a, ...form } = d;
    try {
      setSubmitState(editId ? "Saving changes…" : "Submitting property…");
      const prop = await saveProp.mutateAsync(form as PropertyForm);
      for (const [i, p] of photos.entries()) {
        setSubmitState(`Uploading photo ${i + 1} of ${photos.length}…`);
        await uploadPhoto(prop.id, p.kind, p.blob);
      }
      clear(key);
      navigate(`/bde/properties/${prop.id}`, { replace: true });
    } catch (e) {
      setError(e);
      setSubmitState(null);
    }
  };

  return (
    <div className="mx-auto flex min-h-full max-w-2xl flex-col">
      <div className="sticky top-0 z-10 border-b border-slate-200 bg-white px-4 py-3">
        <div className="flex items-center justify-between">
          <h1 className="font-bold text-slate-900">{editId ? `Edit ${existing.data?.code ?? "property"}` : "Add a property"}</h1>
          {d.savedAt && <span className="text-[11px] text-slate-400">Draft saved on this phone</span>}
        </div>
        {task && <p className="mt-0.5 truncate text-xs text-savo-purple">For task: {task.title}</p>}
        <ol className="mt-2 grid grid-cols-3 gap-2">
          {STEPS.map((s, i) => (
            <li key={s}>
              <button
                type="button"
                disabled={i > step && !stepValid.slice(0, i).every(Boolean)}
                onClick={() => set({ step: i })}
                className={cn("w-full border-t-4 pt-1 text-left text-xs font-semibold",
                  i === step ? "border-savo-purple text-savo-purple" : i < step ? "border-savo-purple/40 text-slate-600" : "border-slate-200 text-slate-400")}
              >
                {i + 1}. {s}
              </button>
            </li>
          ))}
        </ol>
      </div>

      <div className="flex-1 space-y-4 px-4 py-4 pb-28">
        {step === 0 && (
          <>
            <div className="h-72 overflow-hidden rounded-xl border border-slate-200">
              <MapView
                ref={mapRef}
                initialViewState={d.lat !== undefined ? { latitude: d.lat, longitude: d.lon!, zoom: 17 } : task ? { latitude: task.lat, longitude: task.lon, zoom: 16 } : undefined}
                onClick={(e) => set({ lat: e.lngLat.lat, lon: e.lngLat.lng })}
                cursor="crosshair"
              >
                {task && (
                  <Source id="task-area" type="geojson" data={circle(task.lat, task.lon, task.radius_m)}>
                    <Layer id="task-area-fill" type="fill" paint={{ "fill-color": BRAND.yellow, "fill-opacity": 0.15 }} />
                    <Layer id="task-area-line" type="line" paint={{ "line-color": BRAND.purple, "line-dasharray": [2, 2] }} />
                  </Source>
                )}
                {d.gps && (
                  <Marker longitude={d.gps.lon} latitude={d.gps.lat}>
                    <span className="block h-4 w-4 rounded-full border-2 border-white bg-blue-500 shadow" title="Your phone" />
                  </Marker>
                )}
                {d.lat !== undefined && (
                  <Marker longitude={d.lon!} latitude={d.lat} anchor="bottom" draggable
                    onDragEnd={(e) => set({ lat: e.lngLat.lat, lon: e.lngLat.lng })}>
                    <MapPin className="h-9 w-9 fill-savo-yellow text-savo-purple drop-shadow" />
                  </Marker>
                )}
              </MapView>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Button type="button" variant="secondary" onClick={locate} loading={gpsState === "locating"}>
                <LocateFixed className="h-4 w-4" /> Use my location
              </Button>
              {d.gps && (
                <Button type="button" variant="ghost" onClick={() => set({ lat: d.gps!.lat, lon: d.gps!.lon })}>
                  <Crosshair className="h-4 w-4" /> Pin at my position
                </Button>
              )}
            </div>
            <p className="text-xs text-slate-500">
              Tap the map or drag the pin onto the building's entrance.
              {d.gps ? ` Phone location accurate to ~${d.gps.accuracy ?? "?"} m.` : gpsState === "denied" ? " Location permission was denied; place the pin by hand." : ""}
            </p>
            {pinGpsGap !== null && pinGpsGap > 150 && (
              <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                The pin is {pinGpsGap} m from where you are standing. That's fine if you're capturing from elsewhere; otherwise move the pin.
              </div>
            )}
            {check && (
              <Card className="p-3 text-sm">
                {check.in_region ? (
                  <p>
                    <span className="font-semibold">{check.locality ?? "Chennai"}</span>
                    {check.pincode && <span className="text-slate-500"> · {check.pincode}</span>}
                    {check.rent_band && (
                      <span className="mt-1 block text-xs text-slate-500">
                        Typical ground-floor rent here: ₹{check.rent_band.min}–{check.rent_band.max}/sq ft/month <Badge tone="highlight">MOCK</Badge>
                      </span>
                    )}
                  </p>
                ) : (
                  <p className="font-semibold text-red-700">This pin is outside the Chennai Metropolitan Area.</p>
                )}
                {check.duplicates.length > 0 && (
                  <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3">
                    <p className="font-semibold text-amber-900">Is this the same place?</p>
                    <ul className="mt-1 space-y-1 text-amber-900">
                      {check.duplicates.map((x) => (
                        <li key={x.id}>
                          {x.code} · {x.name} <span className="text-xs">({Math.round(x.dist_m)} m away, {x.stage.toLowerCase().replace("_", " ")})</span>
                        </li>
                      ))}
                    </ul>
                    <label className="mt-2 flex items-center gap-2 font-medium">
                      <input type="checkbox" className="h-5 w-5 accent-savo-purple" checked={!!d.confirmed_not_duplicate}
                        onChange={(e) => set({ confirmed_not_duplicate: e.target.checked })} />
                      No, it's a different property
                    </label>
                  </div>
                )}
              </Card>
            )}
          </>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <Field label="Name" required hint="e.g. building or shop name, so the team can recognise it">
              <input className={inputCls} value={d.name ?? ""} onChange={(e) => set({ name: e.target.value })} placeholder="Sri Lakshmi Complex, ground floor" />
            </Field>
            <Field label="Landmark">
              <input className={inputCls} value={d.landmark ?? ""} onChange={(e) => set({ landmark: e.target.value })} placeholder="Opp. bus stop" />
            </Field>
            <Field label="Type">
              <Chips value={d.property_type} onChange={(v) => set({ property_type: v })}
                options={[{ v: "shop", label: "Shop" }, { v: "showroom", label: "Showroom" }, { v: "standalone", label: "Standalone" }, { v: "mall_unit", label: "Mall unit" }, { v: "other", label: "Other" }]} />
            </Field>
            <Field label="Floor" required>
              <Chips value={d.floor} onChange={(v) => set({ floor: v })}
                options={[{ v: "ground", label: "Ground" }, { v: "first", label: "First" }, { v: "basement", label: "Basement" }, { v: "upper", label: "2nd+" }]} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Carpet area" required hint="Target 1,500–4,000">
                <NumberInput value={d.carpet_sqft} onChange={(v) => set({ carpet_sqft: v ?? undefined })} suffix="sq ft" />
              </Field>
              <Field label="Frontage">
                <NumberInput value={d.frontage_ft} onChange={(v) => set({ frontage_ft: v })} suffix="ft" />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Rent per month" hint={d.rent_monthly && d.carpet_sqft ? `≈ ₹${Math.round(d.rent_monthly / d.carpet_sqft)}/sq ft` : "Leave empty if unknown"}>
                <NumberInput value={d.rent_monthly} onChange={(v) => set({ rent_monthly: v })} suffix="₹" />
              </Field>
              <Field label="Deposit">
                <NumberInput value={d.deposit} onChange={(v) => set({ deposit: v })} suffix="₹" />
              </Field>
            </div>
            <Field label="Delivery access">
              <Chips value={d.delivery_access} onChange={(v) => set({ delivery_access: v })}
                options={[{ v: "truck", label: "Truck" }, { v: "van", label: "Van" }, { v: "two_wheeler", label: "2-wheeler only" }, { v: "none", label: "None" }]} />
            </Field>
            <Field label="Visibility">
              <Chips value={d.visibility} onChange={(v) => set({ visibility: v })}
                options={[{ v: "main_road", label: "Main road" }, { v: "side_street", label: "Side street" }, { v: "inside_lane", label: "Inside lane" }]} />
            </Field>
            <div className="grid grid-cols-3 gap-3">
              <Field label="2W parking">
                <NumberInput value={d.parking_2w} onChange={(v) => set({ parking_2w: v })} />
              </Field>
              <Field label="Car parking">
                <NumberInput value={d.parking_4w} onChange={(v) => set({ parking_4w: v })} />
              </Field>
              <Field label="Power">
                <NumberInput value={d.power_kw} onChange={(v) => set({ power_kw: v })} suffix="kW" />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Lease">
                <NumberInput value={d.lease_years} onChange={(v) => set({ lease_years: v })} suffix="yrs" />
              </Field>
              <Field label="Landlord">
                <input className={inputCls} value={d.landlord_name ?? ""} onChange={(e) => set({ landlord_name: e.target.value })} />
              </Field>
            </div>
            <Field label="Landlord phone">
              <input className={inputCls} inputMode="tel" value={d.landlord_phone ?? ""} onChange={(e) => set({ landlord_phone: e.target.value })} />
            </Field>
            <Field label="Notes">
              <textarea className={cn(inputCls, "min-h-20 py-2")} value={d.notes ?? ""} onChange={(e) => set({ notes: e.target.value })} />
            </Field>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">Photos help your manager decide without a visit. They're compressed on your phone before upload.</p>
            <div className="grid grid-cols-3 gap-3">
              {PHOTO_SLOTS.map((s) => {
                const p = photos.find((x) => x.kind === s.kind);
                return (
                  <label key={s.kind} className="relative flex aspect-square cursor-pointer flex-col items-center justify-center overflow-hidden rounded-xl border-2 border-dashed border-slate-300 bg-white text-center text-xs text-slate-500">
                    {p ? <img src={p.url} alt={s.label} className="absolute inset-0 h-full w-full object-cover" /> : <><Camera className="mb-1 h-6 w-6 text-savo-purple" />{s.label}</>}
                    <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => onPhoto(s.kind, e.target.files?.[0])} />
                  </label>
                );
              })}
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-savo-purple">
              <ImagePlus className="h-4 w-4" /> Add another photo
              <input type="file" accept="image/*" className="sr-only" onChange={(e) => onPhoto("other", e.target.files?.[0])} />
            </label>
            {photos.filter((p) => p.kind === "other").map((p, i) => (
              <div key={p.url} className="flex items-center gap-2 text-sm">
                <img src={p.url} alt="" className="h-12 w-12 rounded object-cover" /> Extra photo {i + 1}
                <button type="button" onClick={() => setPhotos((c) => c.filter((x) => x !== p))} aria-label="Remove photo"><Trash2 className="h-4 w-4 text-slate-400" /></button>
              </div>
            ))}
            <Card className="p-3 text-sm">
              <p className="font-semibold">{d.name}</p>
              <p className="text-slate-600">{d.carpet_sqft?.toLocaleString("en-IN")} sq ft · {d.floor} floor · {d.rent_monthly ? `₹${d.rent_monthly.toLocaleString("en-IN")}/month` : "rent not captured"}</p>
              {check?.locality && <p className="text-xs text-slate-500">{check.locality} · {check.pincode}</p>}
            </Card>
          </div>
        )}
        {error ? <ErrorNote error={error} /> : null}
      </div>

      <div className="fixed inset-x-0 bottom-14 z-20 border-t border-slate-200 bg-white px-4 py-3 md:bottom-0 md:left-52">
        <div className="mx-auto flex max-w-2xl gap-2">
          {step > 0 && (
            <Button type="button" variant="secondary" onClick={() => set({ step: step - 1 })} disabled={!!submitState}>
              <ChevronLeft className="h-4 w-4" /> Back
            </Button>
          )}
          {step < 2 ? (
            <Button type="button" className="flex-1" disabled={!stepValid[step]} onClick={() => set({ step: step + 1 })}>
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          ) : (
            <Button type="button" className="flex-1" disabled={!stepValid[0] || !stepValid[1] || !!submitState} onClick={submit}>
              {submitState ? <><Loader2 className="h-4 w-4 animate-spin" /> {submitState}</> : <><Check className="h-4 w-4" /> {editId ? "Save and re-evaluate" : "Submit for evaluation"}</>}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
