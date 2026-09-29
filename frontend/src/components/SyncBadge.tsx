import { useState } from "react";
import { CloudOff, CloudUpload, Check } from "lucide-react";
import { syncNow, useOnline, usePendingCount } from "@/offline/sync";
import { cn } from "@/lib/cn";

/** Header badge for field users: online state + lanes waiting to sync, tap to sync now. */
export function SyncBadge() {
  const online = useOnline();
  const pending = usePendingCount() ?? 0;
  const [busy, setBusy] = useState(false);
  return (
    <button
      onClick={async () => {
        setBusy(true);
        await syncNow();
        setBusy(false);
      }}
      className={cn(
        "flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold",
        !online ? "bg-amber-400 text-amber-950" : pending ? "bg-savo-yellow text-savo-purple" : "bg-white/15 text-white",
      )}
      title={online ? "Tap to sync now" : "Offline: changes are saved on this phone"}
    >
      {!online ? <CloudOff className="h-3.5 w-3.5" /> : pending ? <CloudUpload className={cn("h-3.5 w-3.5", busy && "animate-pulse")} /> : <Check className="h-3.5 w-3.5" />}
      {!online ? `Offline${pending ? ` · ${pending} to sync` : ""}` : pending ? `${pending} to sync` : "Synced"}
    </button>
  );
}
