import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Geometry } from "geojson";
import { api } from "@/api/client";
import type { JobStep } from "@/api/types";

export interface PincodeHit {
  pincode: string;
  office_name: string;
  area_km2: number;
  pop_est: number | null;
  in_cma_share: number;
}

export interface LocalityHit {
  place_id: string;
  name: string;
  display_name: string;
  type: string | null;
  lat: number;
  lon: number;
  has_boundary: boolean;
}

export type AreaInput =
  | { type: "pincode"; pincode: string }
  | { type: "locality"; query: string; place_id: string }
  | { type: "cells"; cells: string[] };

export interface Area {
  id: string;
  name: string;
  selection_type: "pincode" | "locality" | "cells";
  selection_input: Record<string, unknown>;
  area_km2: number;
  n_cells: number;
  geometry: Geometry;
  created_at: string;
}

export type ReportStatus = "queued" | "running" | "completed" | "partial" | "failed";

export interface SubScore {
  key: string;
  label: string;
  weight: number;
  raw_value: number;
  unit: string;
  percentile: number | null;
  score: number;
  contribution: number;
  explain: string;
}

export interface Hotspot {
  id: string;
  rank: number;
  h3: string;
  lat: number;
  lon: number;
  score: number;
  near_road: string | null;
  nearest_store_km: number;
  neighbourhood_population: number | null;
  strengths: { key: string; label: string; score: number }[];
}

export interface Fact {
  label: string;
  value: number | string;
  unit: string;
  source: string;
}

export interface Narrative {
  headline: string;
  summary: string;
  reasons: { text: string; fact_ids: string[] }[];
  scout_first: { hotspot_id: string; text: string }[];
  risks: { text: string; fact_ids: string[] }[];
  caveats: string[];
}

export interface DataSourceRef {
  id: number;
  key: string;
  name: string;
  as_of: string | null;
  is_mock: boolean;
}

export interface ReportMetrics {
  area_km2: number;
  population: number;
  buildings: number;
  residential_buildings: number;
  footfall_points: number;
  competitors: { kirana_convenience: number; supermarket: number; organised_chain: number };
  competitors_in_ring: number;
  retail_shops: number;
  road_major_km: number;
  road_minor_km: number;
  poi_by_category: Record<string, number>;
  organised_chains_nearby: { name: string; n: number }[];
  rail_metro_stations: string[];
  nearest_store: { code: string; name: string; distance_km: number };
  savomart_stores_within_3km: { store_code: string; name: string; dist_m: number }[];
}

export interface ReportSummary {
  id: string;
  area_id: string;
  area_name: string;
  selection_type: string;
  area_km2: number;
  status: ReportStatus;
  overall_score: number | null;
  grade: string | null;
  confidence: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface Report extends ReportSummary {
  scoring_version: string;
  confidence_reasons: string[] | null;
  metrics: ReportMetrics | null;
  sub_scores: SubScore[] | null;
  hotspots: Hotspot[] | null;
  facts: Record<string, Fact> | null;
  narrative: Narrative | null;
  narrative_source: "llm" | "template" | null;
  llm_model: string | null;
  data_sources: DataSourceRef[] | null;
  error: string | null;
  job: { id: string; status: string; steps: JobStep[]; error: string | null } | null;
  area_geometry: Geometry;
  created_by_name: string;
}

export const isTerminal = (s: ReportStatus) => s === "completed" || s === "partial" || s === "failed";

export function usePincodeSearch(q: string) {
  return useQuery({
    queryKey: ["pincodes", q],
    queryFn: () => api<PincodeHit[]>(`/ref/pincodes?q=${encodeURIComponent(q)}`),
    staleTime: Infinity,
  });
}

export function useLocalitySearch() {
  return useMutation({
    mutationFn: (q: string) => api<LocalityHit[]>(`/areas/localities?q=${encodeURIComponent(q)}`),
  });
}

/** Create the area, then queue its report. Returns the new report. */
export function useAnalyseArea() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: AreaInput) => {
      const area = await api<Area>("/areas", { body: input });
      return api<Report>(`/areas/${area.id}/reports`, { method: "POST" });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports"] }),
  });
}

export function useReport(id: string | undefined) {
  return useQuery({
    queryKey: ["report", id],
    queryFn: () => api<Report>(`/reports/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && isTerminal(q.state.data.status) ? false : 1500),
  });
}

export function useReports() {
  return useQuery({ queryKey: ["reports"], queryFn: () => api<ReportSummary[]>("/reports") });
}

export function useCompare(ids: string[]) {
  return useQuery({
    queryKey: ["compare", ids],
    queryFn: () => api<Report[]>(`/reports/compare?ids=${ids.join(",")}`),
    enabled: ids.length >= 2,
  });
}

export function useRetryReport(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<Report>(`/reports/${id}/retry`, { method: "POST" }),
    onSuccess: (r) => qc.setQueryData(["report", id], r),
  });
}
