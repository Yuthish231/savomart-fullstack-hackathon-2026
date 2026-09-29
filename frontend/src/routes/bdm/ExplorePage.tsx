import { MousePointerClick } from "lucide-react";
import { MapView } from "@/map/MapView";
import { PincodeLayer, StoresLayer } from "@/map/layers";
import { useStores } from "@/api/ref";
import { Card } from "@/components/ui";

export function ExplorePage() {
  const stores = useStores();
  return (
    <div className="relative h-full min-h-[calc(100vh-3.5rem-4rem)] md:min-h-0">
      <MapView>
        <PincodeLayer />
        <StoresLayer />
      </MapView>
      <Card className="absolute left-3 top-3 w-[min(22rem,calc(100%-4.5rem))] p-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-savo-purple">
          <MousePointerClick className="h-4 w-4" /> Explore Chennai
        </div>
        <p className="mt-1 text-sm text-slate-600">
          Select an area by pincode, locality or grid cells, then run an Area Fitness Report.
        </p>
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
