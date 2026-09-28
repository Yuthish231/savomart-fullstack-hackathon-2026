import { MousePointerClick } from "lucide-react";
import { MapView } from "@/map/MapView";
import { Card } from "@/components/ui";

export function ExplorePage() {
  return (
    <div className="relative h-full min-h-[calc(100vh-3.5rem-4rem)] md:min-h-0">
      <MapView />
      <Card className="absolute left-3 top-3 w-[min(22rem,calc(100%-4.5rem))] p-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-savo-purple">
          <MousePointerClick className="h-4 w-4" /> Explore Chennai
        </div>
        <p className="mt-1 text-sm text-slate-600">
          Select an area by pincode, locality or grid cells, then run an Area Fitness Report.
        </p>
      </Card>
    </div>
  );
}
