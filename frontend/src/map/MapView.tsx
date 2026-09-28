import type { ReactNode } from "react";
import Map, {
  AttributionControl,
  NavigationControl,
  ScaleControl,
  type ViewState,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";

// Free vector basemap, no API key. Swap for "liberty" for a more detailed street style.
export const BASEMAP_STYLE = "https://tiles.openfreemap.org/styles/positron";

export const CHENNAI_VIEW: Partial<ViewState> = {
  longitude: 80.215,
  latitude: 13.045,
  zoom: 10.6,
};

// Chennai Metropolitan Area, with some slack so users can pan to the edges.
const CMA_BOUNDS: [[number, number], [number, number]] = [
  [79.8, 12.6],
  [80.5, 13.5],
];

export function MapView({ children }: { children?: ReactNode }) {
  return (
    <Map
      initialViewState={CHENNAI_VIEW}
      mapStyle={BASEMAP_STYLE}
      maxBounds={CMA_BOUNDS}
      minZoom={9}
      style={{ width: "100%", height: "100%" }}
      attributionControl={false}
    >
      <NavigationControl position="top-right" showCompass={false} />
      <AttributionControl position="bottom-right" compact />
      <ScaleControl position="bottom-left" unit="metric" />
      {children}
    </Map>
  );
}
