import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Layer, Marker, Source } from "react-map-gl/maplibre";
import type { FeatureCollection } from "geojson";
import { CalendarDays, CheckCircle2, MapPin, Navigation, PlusCircle } from "lucide-react";
import { useTasks, useUpdateTask } from "@/api/properties";
import { MapView } from "@/map/MapView";
import { BRAND, StoresLayer } from "@/map/layers";
import { Badge, Button, Card, EmptyState, ErrorNote, PageHeader, Spinner } from "@/components/ui";

function circles(tasks: { lat: number; lon: number; radius_m: number }[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: tasks.map((t) => ({
      type: "Feature",
      properties: {},
      geometry: {
        type: "Polygon",
        coordinates: [Array.from({ length: 41 }, (_, i) => {
          const a = (i / 40) * 2 * Math.PI;
          return [t.lon + (t.radius_m / (111320 * Math.cos((t.lat * Math.PI) / 180))) * Math.cos(a), t.lat + (t.radius_m / 110540) * Math.sin(a)];
        })],
      },
    })),
  };
}

export function TasksPage() {
  const { data, isLoading, error } = useTasks();
  const update = useUpdateTask();
  const areas = useMemo(() => circles(data ?? []), [data]);
  const first = data?.[0];

  return (
    <div className="mx-auto max-w-3xl p-4 md:p-6">
      <PageHeader title="My scouting tasks" subtitle="Hotspots your manager wants you to scout. Find vacant ground-floor shops nearby." />
      {isLoading && <Spinner />}
      {error && <ErrorNote error={error} />}
      {data?.length === 0 && (
        <EmptyState icon={<MapPin className="h-5 w-5" />} title="No tasks right now"
          body="When your manager assigns a hotspot it appears here. You can still add a property you've spotted."
          action={<Link to="/bde/new"><Button><PlusCircle className="h-4 w-4" /> Add a property</Button></Link>} />
      )}
      {data && data.length > 0 && (
        <>
          <Card className="mb-4 h-56 overflow-hidden">
            <MapView initialViewState={first ? { latitude: first.lat, longitude: first.lon, zoom: 13 } : undefined}>
              <Source id="task-areas" type="geojson" data={areas}>
                <Layer id="task-areas-fill" type="fill" paint={{ "fill-color": BRAND.yellow, "fill-opacity": 0.2 }} />
                <Layer id="task-areas-line" type="line" paint={{ "line-color": BRAND.purple, "line-width": 1.5 }} />
              </Source>
              <StoresLayer />
              {data.map((t, i) => (
                <Marker key={t.id} longitude={t.lon} latitude={t.lat}>
                  <span className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-savo-purple bg-savo-yellow text-xs font-bold text-savo-purple">{i + 1}</span>
                </Marker>
              ))}
            </MapView>
          </Card>
          <div className="space-y-3">
            {data.map((t, i) => (
              <Card key={t.id} className="p-4">
                <div className="flex items-start gap-3">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-savo-purple text-xs font-bold text-savo-yellow">{i + 1}</span>
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-slate-900">{t.title}</div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <span>from {t.assigned_by.name}</span>
                      {t.due_date && <span className="inline-flex items-center gap-1"><CalendarDays className="h-3 w-3" /> due {new Date(t.due_date).toLocaleDateString("en-IN")}</span>}
                      <Badge tone={t.status === "in_progress" ? "brand" : "neutral"}>{t.status.replace("_", " ")}</Badge>
                      {t.properties_found > 0 && <span>{t.properties_found} propert{t.properties_found === 1 ? "y" : "ies"} added</span>}
                    </div>
                    {t.note && <p className="mt-2 rounded bg-slate-50 px-2 py-1 text-sm text-slate-700">“{t.note}”</p>}
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:flex">
                  <Link to={`/bde/new?task=${t.id}`} className="contents">
                    <Button><PlusCircle className="h-4 w-4" /> Add property here</Button>
                  </Link>
                  <a href={`https://www.google.com/maps/dir/?api=1&destination=${t.lat},${t.lon}`} target="_blank" rel="noreferrer" className="contents">
                    <Button variant="secondary"><Navigation className="h-4 w-4" /> Directions</Button>
                  </a>
                  {t.properties_found > 0 && t.status !== "done" && (
                    <Button variant="ghost" loading={update.isPending} onClick={() => update.mutate({ id: t.id, status: "done" })}>
                      <CheckCircle2 className="h-4 w-4" /> Mark done
                    </Button>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
