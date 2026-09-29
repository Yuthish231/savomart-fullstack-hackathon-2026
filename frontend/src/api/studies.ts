import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FeatureCollection, LineString, Geometry } from "geojson";
import { api } from "@/api/client";
import type { JobStep } from "@/api/types";

export type StudyStatus = "REQUESTED" | "PLANNED" | "IN_PROGRESS" | "COMPLETING" | "COMPLETED";

export interface Progress {
  lanes: number;
  done: number;
  skipped: number;
  reused: number;
  draft: number;
  closed_m: number;
  total_m: number;
  closed_share: number;
}

export interface StudySummary {
  id: string;
  code: string;
  title: string;
  target_type: "property" | "area";
  status: StudyStatus;
  reuse_mode: "none" | "partial" | "full";
  reuse_coverage: number;
  radius_m: number;
  due_date: string | null;
  created_at: string;
  completed_at: string | null;
  requested_by: string | null;
  property: { id: string; code: string; name: string; stage: string } | null;
  report_id: string | null;
  progress: Progress;
  households_est: number | null;
}

export interface Chunk {
  id: string;
  label: string;
  status: "unassigned" | "assigned" | "in_progress" | "done";
  effort_m: number;
  lane_count: number;
  assignee_id: string | null;
  assignee: string | null;
  closed: number;
  drafts: number;
  last_sync: string | null;
}

export interface Insight {
  lanes_total: number;
  lanes_observed: number;
  lanes_skipped: number;
  lanes_reused: number;
  coverage: number;
  households_observed: number;
  households_est: number;
  population_est: number;
  assumed_household_size: number;
  density_est: number | null;
  modelled_population: number;
  survey_vs_model: number | null;
  kiranas_observed: number;
  kiranas_est: number;
  lanes_with_organised_chain: number;
  osm_competitors: number;
  affluence_index: number | null;
  housing_mix: Record<string, number>;
  footfall_mix: Record<string, number>;
  delivery_access_mix: Record<string, number>;
  skip_reasons: Record<string, number>;
  includes_seed_data: boolean;
  captured_from: string | null;
  captured_to: string | null;
  source_studies: { id: string; code: string }[];
}

export interface StudyDetail extends StudySummary {
  notes: string | null;
  total_length_m: number;
  reused_studies: { id: string; code: string; completed_at: string | null }[];
  chunks: Chunk[];
  insight: Insight | null;
  insight_narrative: {
    headline: string;
    summary: string;
    reasons: { text: string; fact_ids: string[] }[];
    risks: { text: string; fact_ids: string[] }[];
    caveats: string[];
    source?: string;
    model?: string;
  } | null;
  job: { status: string; steps: JobStep[]; error: string | null } | null;
  geometry: Geometry;
  team: { id: string; name: string; open_chunks: number }[];
  can_complete_at: number;
}

export interface LaneProps {
  id: string;
  status: "todo" | "draft" | "done" | "skipped" | "reused";
  chunk_id?: string | null;
  chunk?: string | null;
  name: string | null;
  highway: string;
  length_m: number;
  survey?: { client_uuid: string; status: string; data: LaneData; version: number; captured_at: string } | null;
}

export interface LaneData {
  housing_type?: "independent" | "apartments" | "mixed" | "informal" | "commercial";
  dwellings_bucket?: "0-10" | "11-25" | "26-50" | "51-100" | "100+";
  condition?: "new" | "maintained" | "old" | "dilapidated";
  vehicles?: "mostly_2w" | "mixed" | "many_cars";
  kiranas?: number;
  kirana_names?: string;
  organised_present?: boolean;
  footfall?: "low" | "medium" | "high";
  delivery_access?: "truck" | "van" | "two_wheeler" | "none";
  skip_reason?: "gated" | "under_construction" | "not_residential" | "inaccessible" | "other";
  notes?: string;
}

export interface ChunkDetail {
  chunk: { id: string; label: string; status: string; effort_m: number; lane_count: number };
  study: { id: string; code: string; title: string; status: StudyStatus; due_date: string | null };
  lanes: FeatureCollection<LineString, LaneProps>;
}

export interface MyChunk {
  id: string;
  label: string;
  status: string;
  effort_m: number;
  lane_count: number;
  study_id: string;
  code: string;
  title: string;
  due_date: string | null;
  study_status: StudyStatus;
  closed: number;
  drafts: number;
}

const running = (s?: StudyDetail) => !!s && (s.status === "COMPLETING" || s.job?.status === "running" || s.job?.status === "queued");

export function useStudies(filter: { status?: string; property_id?: string; report_id?: string } = {}) {
  const qs = new URLSearchParams(Object.entries(filter).filter(([, v]) => v) as [string, string][]).toString();
  return useQuery({ queryKey: ["studies", filter], queryFn: () => api<StudySummary[]>(`/studies${qs ? `?${qs}` : ""}`) });
}

export function useStudy(id: string | undefined) {
  return useQuery({
    queryKey: ["study", id],
    queryFn: () => api<StudyDetail>(`/studies/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (running(q.state.data) ? 1500 : 15_000),
  });
}

export function useStudyLanes(id: string | undefined, version: string) {
  return useQuery({
    queryKey: ["study-lanes", id, version],
    queryFn: () => api<FeatureCollection<LineString, LaneProps>>(`/studies/${id}/lanes.geojson`),
    enabled: !!id,
  });
}

export function useStudyActions(id: string) {
  const qc = useQueryClient();
  const done = (s: StudyDetail) => {
    qc.setQueryData(["study", id], s);
    qc.invalidateQueries({ queryKey: ["study-lanes", id] });
    qc.invalidateQueries({ queryKey: ["studies"] });
  };
  return {
    plan: useMutation({ mutationFn: (target: number) => api<StudyDetail>(`/studies/${id}/plan`, { body: { target_effort_m: target } }), onSuccess: done }),
    assign: useMutation({
      mutationFn: (b: { chunk: string; assignee: string | null }) => api<StudyDetail>(`/chunks/${b.chunk}`, { method: "PATCH", body: { assignee_id: b.assignee } }),
      onSuccess: done,
    }),
    complete: useMutation({ mutationFn: (force_reason?: string) => api<StudyDetail>(`/studies/${id}/complete`, { body: { force_reason } }), onSuccess: done }),
    resurvey: useMutation({ mutationFn: (reason: string) => api<StudyDetail>(`/studies/${id}/resurvey`, { body: { reason } }), onSuccess: done }),
  };
}

export function useRequestStudy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { target_type: "property" | "area"; property_id?: string; report_id?: string; radius_m?: number; notes?: string }) =>
      api<StudyDetail>("/studies", { body: b }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["studies"] }),
  });
}

export function useMyChunks() {
  return useQuery({ queryKey: ["my-chunks"], queryFn: () => api<MyChunk[]>("/chunks") });
}
