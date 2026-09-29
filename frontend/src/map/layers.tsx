import { useMemo, useState } from "react";
import { cellToBoundary } from "h3-js";
import type { FeatureCollection, Polygon } from "geojson";
import { Layer, Marker, Popup, Source } from "react-map-gl/maplibre";
import { useOpportunity, usePincodeLayer, useStores, type OpportunityCell, type StoreProps } from "@/api/ref";

export const BRAND = { purple: "#782B90", yellow: "#FFF200" } as const;

/** Existing Savomart stores: purple pins with a yellow core. Click for details. */
export function StoresLayer() {
  const { data } = useStores();
  const [open, setOpen] = useState<{ props: StoreProps; lng: number; lat: number } | null>(null);
  if (!data) return null;
  return (
    <>
      {data.features.map((f) => {
        const [lng, lat] = f.geometry.coordinates;
        return (
          <Marker
            key={f.properties.store_code}
            longitude={lng}
            latitude={lat}
            anchor="bottom"
            onClick={(e) => {
              e.originalEvent.stopPropagation();
              setOpen({ props: f.properties, lng, lat });
            }}
          >
            <svg width="26" height="34" viewBox="0 0 26 34" className="cursor-pointer drop-shadow" aria-label={f.properties.name}>
              <path d="M13 0C5.8 0 0 5.6 0 12.6 0 22 13 34 13 34s13-12 13-21.4C26 5.6 20.2 0 13 0z" fill={BRAND.purple} />
              <circle cx="13" cy="12.5" r="5" fill={BRAND.yellow} />
            </svg>
          </Marker>
        );
      })}
      {open && (
        <Popup longitude={open.lng} latitude={open.lat} anchor="top" onClose={() => setOpen(null)} maxWidth="260px">
          <div className="text-xs font-semibold uppercase tracking-wide text-savo-purple">Savomart store</div>
          <div className="font-semibold text-slate-900">{open.props.name}</div>
          <div className="mt-1 text-xs text-slate-500">{open.props.address}</div>
          <div className="mt-1 text-xs text-slate-400">
            {open.props.store_code} · pincode {open.props.pincode ?? "n/a"} (from coordinates)
          </div>
        </Popup>
      )}
    </>
  );
}

export function h3ToFeatures<P extends { h3: string }>(cells: P[]): FeatureCollection<Polygon, P> {
  return {
    type: "FeatureCollection",
    features: cells.map((c) => {
      const ring = cellToBoundary(c.h3, true); // [lng, lat] pairs, closed
      return { type: "Feature", geometry: { type: "Polygon", coordinates: [ring] }, properties: c };
    }),
  };
}

// Sequential ramp from pale lilac to brand purple; the best cells get a yellow edge.
export const OPPORTUNITY_STOPS: [number, string][] = [
  [30, "#F3E9F6"],
  [45, "#D9B8E3"],
  [55, "#B57BC7"],
  [65, "#8E3FA6"],
  [75, "#5A1F6C"],
];

/** City-wide opportunity heatmap (H3 res 8), same scoring model as the area report. */
export function OpportunityLayer({ visible }: { visible: boolean }) {
  const { data } = useOpportunity(visible);
  const fc = useMemo(() => (data ? h3ToFeatures<OpportunityCell>(data) : null), [data]);
  if (!fc || !visible) return null;
  return (
    <Source id="opportunity" type="geojson" data={fc}>
      <Layer
        id="opportunity-fill"
        type="fill"
        beforeId="pincode-fill"
        paint={{
          "fill-color": ["interpolate", ["linear"], ["get", "score"], ...OPPORTUNITY_STOPS.flat()],
          "fill-opacity": 0.62,
        }}
      />
      <Layer
        id="opportunity-top"
        type="line"
        beforeId="pincode-fill"
        filter={[">=", ["get", "score"], 72]}
        paint={{ "line-color": BRAND.yellow, "line-width": 1.6 }}
      />
    </Source>
  );
}

/** Pincode boundaries with labels; `highlight` outlines the selected pincode. */
const EMPTY_FC: FeatureCollection = { type: "FeatureCollection", features: [] };

export function PincodeLayer({ highlight }: { highlight?: string | null }) {
  const { data } = usePincodeLayer();
  // Mount immediately (empty until loaded) so other layers can anchor below "pincode-fill".
  return (
    <Source id="pincodes" type="geojson" data={data ?? EMPTY_FC}>
      <Layer
        id="pincode-fill"
        type="fill"
        paint={{
          "fill-color": BRAND.purple,
          "fill-opacity": ["case", ["==", ["get", "pincode"], highlight ?? ""], 0.18, 0.02],
        }}
      />
      <Layer
        id="pincode-line"
        type="line"
        paint={{
          "line-color": BRAND.purple,
          "line-opacity": 0.45,
          "line-width": ["case", ["==", ["get", "pincode"], highlight ?? ""], 2.5, 0.8],
        }}
      />
      <Layer
        id="pincode-label"
        type="symbol"
        minzoom={11.5}
        layout={{
          "text-field": ["get", "pincode"],
          "text-size": 11,
          "text-font": ["Noto Sans Regular"],
        }}
        paint={{ "text-color": BRAND.purple, "text-halo-color": "#fff", "text-halo-width": 1.2 }}
      />
    </Source>
  );
}
