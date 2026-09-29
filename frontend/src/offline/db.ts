import Dexie, { type Table } from "dexie";
import type { ChunkDetail, LaneData } from "@/api/studies";

/** A lane survey as the phone holds it. Written on every field change; synced when possible. */
export interface LocalSurvey {
  client_uuid: string;
  study_id: string;
  chunk_id: string;
  lane_id: string;
  status: "draft" | "submitted" | "skipped";
  data: LaneData;
  captured_at: string;
  updated_at: string;
  base_version: number | null; // server version this edit was based on
  synced: 0 | 1;
  conflict?: string | null;
}

export interface CachedChunk {
  chunk_id: string;
  payload: ChunkDetail;
  cached_at: string;
}

class FieldDB extends Dexie {
  surveys!: Table<LocalSurvey, string>;
  chunks!: Table<CachedChunk, string>;

  constructor() {
    super("sitescout-field");
    this.version(1).stores({
      surveys: "client_uuid, chunk_id, [chunk_id+lane_id], synced, study_id",
      chunks: "chunk_id",
    });
  }
}

export const fieldDb = new FieldDB();
