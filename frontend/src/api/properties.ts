import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Fact } from "@/api/areas";
import type { JobStep, Role } from "@/api/types";

export type Stage =
  | "SIGHTED" | "EVALUATED" | "SHORTLISTED" | "SITE_VISIT" | "NEGOTIATION"
  | "CATCHMENT_STUDY" | "FINAL_REVIEW" | "APPROVED" | "ON_HOLD" | "REJECTED";
export type Recommendation = "proceed" | "review" | "reject";

export interface Flag {
  code: string;
  severity: "high" | "medium" | "low";
  message: string;
  related?: string;
}

export interface PropertyForm {
  name: string;
  lat: number;
  lon: number;
  gps?: { lat: number; lon: number; accuracy: number | null } | null;
  address?: string;
  landmark?: string;
  property_type: "shop" | "showroom" | "standalone" | "mall_unit" | "other";
  floor: "ground" | "first" | "basement" | "upper";
  carpet_sqft: number;
  frontage_ft?: number | null;
  rent_monthly?: number | null;
  deposit?: number | null;
  lease_years?: number | null;
  parking_2w?: number | null;
  parking_4w?: number | null;
  power_kw?: number | null;
  delivery_access?: "truck" | "van" | "two_wheeler" | "none" | null;
  visibility?: "main_road" | "side_street" | "inside_lane" | null;
  landlord_name?: string;
  landlord_phone?: string;
  notes?: string;
  scouting_task_id?: string | null;
  confirmed_not_duplicate?: boolean;
}

export interface Duplicate {
  id: string;
  code: string;
  name: string;
  stage: Stage;
  dist_m: number;
  sim: number;
}

export interface PrecheckResult {
  in_region: boolean;
  pincode: string | null;
  locality: string | null;
  rent_band: { min: number; max: number; is_mock: true } | null;
  duplicates: Duplicate[];
}

export interface Check {
  key: string;
  label: string;
  weight: number;
  value: string;
  score: number | null;
  status: "good" | "ok" | "poor" | "blocker" | "unknown";
  note: string;
}

export interface Insight {
  code: string;
  text: string;
  fact_ids: string[];
  severity?: "high" | "medium" | "low";
}

export interface EvaluationContext {
  population_1km: number;
  population_source: string;
  nearest_stores: { code: string; name: string; distance_km: number }[];
  competitors_500m: { name: string; tier: number; dist_m: number }[];
  frontage_road: { name: string | null; highway: string; dist_m: number } | null;
  rent_band: { pincode: string; tier: string; min: number; max: number; is_mock: true } | null;
  footfall_500m: { category: string; n: number }[];
  location_subs?: { key: string; label: string; score: number; raw_value: number; unit: string }[];
  blockers?: string[];
}

export interface Evaluation {
  id: string;
  version: number;
  trigger: string;
  status: "queued" | "running" | "completed" | "partial" | "failed";
  score: number | null;
  location_score: number | null;
  site_score: number | null;
  recommendation: Recommendation | null;
  checks: Check[] | null;
  insights: Insight[] | null;
  risks: Insight[] | null;
  context: EvaluationContext | null;
  facts: Record<string, Fact> | null;
  narrative: {
    headline: string;
    summary: string;
    reasons: { text: string; fact_ids: string[] }[];
    risks: { text: string; fact_ids: string[] }[];
    next_step: string;
    caveats: string[];
  } | null;
  narrative_source: "llm" | "template" | null;
  llm_model: string | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  job: { status: string; steps: JobStep[]; error: string | null } | null;
}

export interface TimelineEvent {
  id: string;
  kind: "stage" | "evaluation" | "note" | "edit";
  from_stage: Stage | null;
  to_stage: Stage | null;
  reason: string | null;
  data: Record<string, unknown> | null;
  at: string;
  actor: string | null;
  actor_role: Role | null;
}

export interface PropertyDetail {
  id: string;
  code: string;
  name: string;
  stage: Stage;
  stage_label: string;
  lat: number;
  lon: number;
  gps: { lat: number; lon: number; accuracy: number | null } | null;
  address: string | null;
  landmark: string | null;
  pincode: string | null;
  details: Record<string, string | number>;
  rent_monthly: number | null;
  carpet_sqft: number | null;
  flags: Flag[];
  duplicate_of: string | null;
  latest_score: number | null;
  latest_recommendation: Recommendation | null;
  previous_score: number | null;
  created_by: { id: string; name: string };
  created_at: string;
  updated_at: string;
  scouting_task: { id: string; title: string } | null;
  evaluation: Evaluation | null;
  last_completed_evaluation: Evaluation | null;
  photos: { id: string; kind: string; path: string }[];
  events: TimelineEvent[];
  allowed_transitions: { to: string; label: string; reason_required: boolean }[];
  studies: { id: string; code: string; status: string; reuse_mode: string; reuse_coverage: number; households_est: number | null }[];
  labels: Record<string, Record<string, string>>;
}

export interface PropertySummary {
  id: string;
  code: string;
  name: string;
  stage: Stage;
  latest_score: number | null;
  latest_recommendation: Recommendation | null;
  flags: Flag[];
  pincode: string | null;
  carpet_sqft: number | null;
  rent_monthly: number | null;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  lat: number;
  lon: number;
  cover_photo: string | null;
}

export interface StageInfo {
  key: Stage;
  label: string;
  description: string;
}

const evalRunning = (p?: PropertyDetail) =>
  !!p?.evaluation && (p.evaluation.status === "queued" || p.evaluation.status === "running");

export function useProperties(enabled = true) {
  return useQuery({ queryKey: ["properties"], queryFn: () => api<PropertySummary[]>("/properties"), enabled });
}

export function useStages() {
  return useQuery({ queryKey: ["stages"], queryFn: () => api<StageInfo[]>("/pipeline/stages"), staleTime: Infinity });
}

export function useProperty(id: string | undefined) {
  return useQuery({
    queryKey: ["property", id],
    queryFn: () => api<PropertyDetail>(`/properties/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (evalRunning(q.state.data) ? 1500 : false),
  });
}

export function usePrecheck() {
  return useMutation({
    mutationFn: (b: { lat: number; lon: number; name: string; landmark?: string }) =>
      api<PrecheckResult>("/properties/check", { body: b }),
  });
}

export function useSaveProperty(editId?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (form: PropertyForm) =>
      editId
        ? api<PropertyDetail>(`/properties/${editId}`, { method: "PATCH", body: form as unknown as Record<string, unknown> })
        : api<PropertyDetail>("/properties", { body: form as unknown as Record<string, unknown> }),
    onSuccess: (p) => {
      qc.setQueryData(["property", p.id], p);
      qc.invalidateQueries({ queryKey: ["properties"] });
      qc.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

export async function uploadPhoto(propertyId: string, kind: string, blob: Blob, attempts = 3) {
  let last: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      const fd = new FormData();
      fd.append("kind", kind);
      fd.append("file", blob, `${kind}.jpg`);
      return await api<{ path: string }>(`/properties/${propertyId}/photos`, { body: fd });
    } catch (e) {
      last = e;
      await new Promise((r) => setTimeout(r, 1000 * (i + 1)));
    }
  }
  throw last;
}

export function usePropertyAction(id: string) {
  const qc = useQueryClient();
  const done = (p: PropertyDetail) => {
    qc.setQueryData(["property", id], p);
    qc.invalidateQueries({ queryKey: ["properties"] });
  };
  return {
    transition: useMutation({
      mutationFn: (b: { to: string; reason?: string }) =>
        api<PropertyDetail>(`/properties/${id}/transitions`, { body: b }),
      onSuccess: done,
    }),
    note: useMutation({
      mutationFn: (text: string) => api<PropertyDetail>(`/properties/${id}/notes`, { body: { text } }),
      onSuccess: done,
    }),
    reevaluate: useMutation({
      mutationFn: () => api<PropertyDetail>(`/properties/${id}/reevaluate`, { method: "POST" }),
      onSuccess: done,
    }),
  };
}

// --- scouting tasks ----------------------------------------------------------------------

export interface ScoutingTask {
  id: string;
  title: string;
  note: string | null;
  lat: number;
  lon: number;
  radius_m: number;
  status: "open" | "in_progress" | "done" | "cancelled";
  due_date: string | null;
  report_id: string | null;
  hotspot_id: string | null;
  area_name: string | null;
  assignee: { id: string; name: string };
  assigned_by: { id: string; name: string };
  properties_found: number;
  created_at: string;
}

export interface TeamMember {
  id: string;
  name: string;
  role: Role;
  role_label: string;
  open_tasks: number;
}

export function useTasks(reportId?: string) {
  return useQuery({
    queryKey: ["tasks", reportId ?? "mine"],
    queryFn: () => api<ScoutingTask[]>(`/scouting-tasks${reportId ? `?report_id=${reportId}` : ""}`),
  });
}

export function useTeam(role: Role, enabled = true) {
  return useQuery({ queryKey: ["team", role], queryFn: () => api<TeamMember[]>(`/users?role=${role}`), enabled });
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { report_id: string; hotspot_id?: string | null; assignee_id: string; note?: string; due_date?: string | null }) =>
      api<ScoutingTask>("/scouting-tasks", { body: b }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["team"] });
    },
  });
}

export function useUpdateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { id: string; status: ScoutingTask["status"] }) =>
      api<ScoutingTask>(`/scouting-tasks/${b.id}`, { method: "PATCH", body: { status: b.status } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}
