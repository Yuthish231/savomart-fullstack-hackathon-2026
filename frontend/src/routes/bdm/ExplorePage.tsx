import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { latLngToCell } from "h3-js";
import { Layer, Marker, Source, type MapLayerMouseEvent, type MapRef } from "react-map-gl/maplibre";
import { Flame, Grid3x3, Hash, MapPin, Search, Sparkles, X } from "lucide-react";
import { MapView } from "@/map/MapView";
import { BRAND, OPPORTUNITY_STOPS, OpportunityLayer, PincodeLayer, StoresLayer, h3ToFeatures } from "@/map/layers";
import { useOpportunity, useStores } from "@/api/ref";
import { useAnalyseArea, useLocalitySearch, usePincodeSearch, type AreaInput, type LocalityHit } from "@/api/areas";
import { Button, Card, ErrorNote, Spinner } from "@/components/ui";
import { cn } from "@/lib/cn";

type Mode = "pincode" | "locality" | "cells";

const MODES: { key: Mode; label: string; icon: typeof Hash }[] = [
  { key: "pincode", label: "Pincode", icon: Hash },
  { key: "locality", label: "Locality", icon: Search },
  { key: "cells", label: "Grid cells", icon: Grid3x3 },
];

export function ExplorePage() {
  const navigate = useNavigate();
  const mapRef = useRef<MapRef>(null);
  const stores = useStores();
  const [showOpp, setShowOpp] = useState(true);
  const opp = useOpportunity(showOpp);

  const [mode, setMode] = useState<Mode>("pincode");
  const [pincode, setPincode] = useState<string | null>(null);
  const [pinQuery, setPinQuery] = useState("");
  const pinHits = usePincodeSearch(pinQuery.trim());
  const [locQuery, setLocQuery] = useState("");
  const locSearch = useLocalitySearch();
  const [locality, setLocality] = useState<LocalityHit | null>(null);
  const [cells, setCells] = useState<string[]>([]);
  const analyse = useAnalyseArea();

  const cellFc = useMemo(() => h3ToFeatures(cells.map((h3) => ({ h3 }))), [cells]);

  const selection: AreaInput | null =
    mode === "pincode" && pincode
      ? { type: "pincode", pincode }
      : mode === "locality" && locality
        ? { type: "locality", query: locQuery, place_id: locality.place_id }
        : mode === "cells" && cells.length
          ? { type: "cells", cells }
          : null;

  const selectionLabel =
    mode === "pincode" && pincode
      ? `${pincode} · ${pinHits.data?.find((p) => p.pincode === pincode)?.office_name ?? ""}`
      : mode === "locality" && locality
        ? locality.name
        : mode === "cells" && cells.length
          ? `${cells.length} grid cell${cells.length > 1 ? "s" : ""} (~${(cells.length * 0.74).toFixed(1)} km²)`
          : null;

  const onMapClick = (e: MapLayerMouseEvent) => {
    if (mode === "cells") {
      const c = latLngToCell(e.lngLat.lat, e.lngLat.lng, 8);
      setCells((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : prev.length >= 60 ? prev : [...prev, c]));
      return;
    }
    const f = e.features?.find((x) => x.layer.id === "pincode-fill");
    if (f) {
      setMode("pincode");
      setPincode(String(f.properties?.pincode));
      setPinQuery(String(f.properties?.pincode));
    }
  };

  const run = () =>
    selection && analyse.mutate(selection, { onSuccess: (r) => navigate(`/bdm/reports/${r.id}`) });

  return (
    <div className="relative h-full min-h-[calc(100vh-3.5rem-4rem)] md:min-h-0">
      <MapView
        ref={mapRef}
        onClick={onMapClick}
        interactiveLayerIds={["pincode-fill"]}
        cursor={mode === "cells" ? "crosshair" : undefined}
      >
        <PincodeLayer highlight={mode === "pincode" ? pincode : null} />
        <OpportunityLayer visible={showOpp} />
        {mode === "cells" && (
          <Source id="sel-cells" type="geojson" data={cellFc}>
            <Layer id="sel-cells-fill" type="fill" paint={{ "fill-color": BRAND.yellow, "fill-opacity": 0.45 }} />
            <Layer id="sel-cells-line" type="line" paint={{ "line-color": BRAND.purple, "line-width": 2 }} />
          </Source>
        )}
        {mode === "locality" && locality && (
          <Marker longitude={locality.lon} latitude={locality.lat} anchor="bottom">
            <MapPin className="h-8 w-8 fill-savo-yellow text-savo-purple" />
          </Marker>
        )}
        <StoresLayer />
      </MapView>

      <Card className="absolute left-3 top-3 max-h-[calc(100%-1.5rem)] w-[min(23rem,calc(100%-4.5rem))] overflow-y-auto p-4">
        <h2 className="text-sm font-semibold text-savo-purple">Which area should we analyse?</h2>

        <div className="mt-3 grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1" role="tablist">
          {MODES.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              role="tab"
              aria-selected={mode === key}
              onClick={() => setMode(key)}
              className={cn(
                "flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-semibold text-slate-600",
                mode === key && "bg-white text-savo-purple shadow-sm",
              )}
            >
              <Icon className="h-3.5 w-3.5" /> {label}
            </button>
          ))}
        </div>

        {mode === "pincode" && (
          <div className="mt-3">
            <input
              value={pinQuery}
              onChange={(e) => setPinQuery(e.target.value)}
              placeholder="Pincode or area name, e.g. 600041 or Velachery"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-savo-purple focus:outline-none"
            />
            <p className="mt-1 text-[11px] text-slate-500">…or click a pincode on the map.</p>
            <ul className="mt-2 max-h-44 overflow-y-auto">
              {pinHits.data?.slice(0, 8).map((p) => (
                <li key={p.pincode}>
                  <button
                    onClick={() => setPincode(p.pincode)}
                    className={cn(
                      "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-savo-purple-light",
                      pincode === p.pincode && "bg-savo-purple-light",
                    )}
                  >
                    <span>
                      <span className="font-semibold">{p.pincode}</span>{" "}
                      <span className="text-slate-600">{p.office_name}</span>
                    </span>
                    <span className="text-[11px] text-slate-400">{p.area_km2.toFixed(1)} km²</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {mode === "locality" && (
          <div className="mt-3">
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setLocality(null);
                if (locQuery.trim().length >= 3) locSearch.mutate(locQuery.trim());
              }}
            >
              <input
                value={locQuery}
                onChange={(e) => setLocQuery(e.target.value)}
                placeholder="e.g. Velachery, Anna Nagar"
                className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-savo-purple focus:outline-none"
              />
              <Button type="submit" variant="secondary" loading={locSearch.isPending} aria-label="Search">
                <Search className="h-4 w-4" />
              </Button>
            </form>
            {locSearch.error && <div className="mt-2"><ErrorNote error={locSearch.error} /></div>}
            {locSearch.data?.length === 0 && (
              <p className="mt-2 text-sm text-slate-500">No match inside Chennai. Try a nearby locality or a pincode.</p>
            )}
            <ul className="mt-2 max-h-44 overflow-y-auto">
              {locSearch.data?.map((l) => (
                <li key={l.place_id}>
                  <button
                    onClick={() => {
                      setLocality(l);
                      mapRef.current?.flyTo({ center: [l.lon, l.lat], zoom: 13 });
                    }}
                    className={cn(
                      "w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-savo-purple-light",
                      locality?.place_id === l.place_id && "bg-savo-purple-light",
                    )}
                  >
                    <span className="font-semibold">{l.name}</span>
                    <span className="block truncate text-[11px] text-slate-500">{l.display_name}</span>
                    <span className="text-[11px] text-slate-400">
                      {l.has_boundary ? "OSM boundary" : "1.2 km around the locality point"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {mode === "cells" && (
          <div className="mt-3 text-sm text-slate-600">
            <p>Click hexagons on the map to add or remove them (~0.74 km² each, up to 60).</p>
            {cells.length > 0 && (
              <button onClick={() => setCells([])} className="mt-2 flex items-center gap-1 text-xs font-semibold text-savo-purple">
                <X className="h-3 w-3" /> Clear {cells.length} cell{cells.length > 1 ? "s" : ""}
              </button>
            )}
          </div>
        )}

        <div className="mt-4 border-t border-slate-100 pt-3">
          {selectionLabel ? (
            <p className="mb-2 text-sm">
              Selected: <span className="font-semibold text-slate-900">{selectionLabel}</span>
            </p>
          ) : (
            <p className="mb-2 text-sm text-slate-500">Nothing selected yet.</p>
          )}
          <Button className="w-full" disabled={!selection} loading={analyse.isPending} onClick={run}>
            <Sparkles className="h-4 w-4" /> Run Area Fitness Report
          </Button>
          {analyse.error && <div className="mt-2"><ErrorNote error={analyse.error} /></div>}
        </div>

        <button
          onClick={() => setShowOpp((v) => !v)}
          aria-pressed={showOpp}
          className={cn(
            "mt-4 flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-sm",
            showOpp ? "border-savo-purple bg-savo-purple-light text-savo-purple" : "border-slate-200 text-slate-600",
          )}
        >
          <span className="flex items-center gap-2 font-medium">
            <Flame className="h-4 w-4" /> Opportunity heatmap
          </span>
          <span className="text-xs">{showOpp ? (opp.isLoading ? <Spinner label="" /> : "on") : "off"}</span>
        </button>
        {showOpp && (
          <div className="mt-2">
            <div
              className="h-2 rounded-full"
              style={{ background: `linear-gradient(to right, ${OPPORTUNITY_STOPS.map(([, c]) => c).join(", ")})` }}
            />
            <div className="mt-1 flex justify-between text-[11px] text-slate-500">
              <span>weaker fit</span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-2.5 w-2.5 border-2 border-savo-yellow bg-savo-purple-dark" /> top pockets
              </span>
              <span>stronger fit</span>
            </div>
            <p className="mt-1 text-[11px] leading-snug text-slate-500">
              Each ~0.7 km² hex scored with the same model as the report: demand, homes, footfall, competition,
              Savomart network fit and access.
            </p>
          </div>
        )}

        <div className="mt-3 flex items-center gap-4 border-t border-slate-100 pt-3 text-xs text-slate-600">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-full border-2 border-savo-yellow bg-savo-purple" />
            Savomart store{stores.data ? ` (${stores.data.features.length})` : ""}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-4 border border-savo-purple/50" /> Pincode
          </span>
        </div>
      </Card>
    </div>
  );
}
