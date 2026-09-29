import { useEffect, useState } from "react";
import { useLiveQuery } from "dexie-react-hooks";
import { api, ApiError } from "@/api/client";
import { fieldDb, type LocalSurvey } from "@/offline/db";

/** Push every unsynced lane survey. Each PUT reuses the phone's client_uuid, so a retry after a
 *  dropped connection can never create a duplicate on the server. */
let running = false;

export async function syncNow(): Promise<{ sent: number; failed: number }> {
  if (running || !navigator.onLine) return { sent: 0, failed: 0 };
  running = true;
  let sent = 0;
  let failed = 0;
  try {
    const pending = await fieldDb.surveys.where("synced").equals(0).toArray();
    for (const s of pending) {
      try {
        const res = await api<{ version: number }>(`/lane-surveys/${s.client_uuid}`, {
          method: "PUT",
          body: {
            study_id: s.study_id, lane_id: s.lane_id, status: s.status, data: s.data as Record<string, unknown>,
            base_version: s.base_version, captured_at: s.captured_at,
          },
        });
        // Only mark synced if nothing changed locally while the request was in flight.
        await fieldDb.transaction("rw", fieldDb.surveys, async () => {
          const cur = await fieldDb.surveys.get(s.client_uuid);
          if (cur && cur.updated_at === s.updated_at) {
            await fieldDb.surveys.update(s.client_uuid, { synced: 1, base_version: res.version, conflict: null });
          } else if (cur) {
            await fieldDb.surveys.update(s.client_uuid, { base_version: res.version });
          }
        });
        sent++;
      } catch (e) {
        failed++;
        if (e instanceof ApiError && e.status === 409) {
          await fieldDb.surveys.update(s.client_uuid, { conflict: e.message });
        } else if (e instanceof ApiError && e.status === 0) {
          break; // offline again: stop and wait for the next attempt
        } else if (e instanceof ApiError) {
          await fieldDb.surveys.update(s.client_uuid, { conflict: e.message });
        }
      }
    }
  } finally {
    running = false;
  }
  return { sent, failed };
}

/** Background sync: on reconnect, every 20 s, and when the app regains focus. */
export function useSyncEngine(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const go = () => void syncNow();
    go();
    const t = setInterval(go, 20_000);
    window.addEventListener("online", go);
    document.addEventListener("visibilitychange", go);
    return () => {
      clearInterval(t);
      window.removeEventListener("online", go);
      document.removeEventListener("visibilitychange", go);
    };
  }, [enabled]);
}

export function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

export function usePendingCount() {
  return useLiveQuery(() => fieldDb.surveys.where("synced").equals(0).count(), [], 0);
}

export async function saveLocal(s: Omit<LocalSurvey, "synced" | "updated_at">) {
  await fieldDb.surveys.put({ ...s, synced: 0, updated_at: new Date().toISOString(), conflict: null });
}
