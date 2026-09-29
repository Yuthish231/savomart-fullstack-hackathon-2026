import { useQuery } from "@tanstack/react-query";
import type { FeatureCollection, Point, MultiPolygon } from "geojson";
import { api } from "@/api/client";

export interface StoreProps {
  store_code: string;
  name: string;
  address: string | null;
  pincode: string | null;
}

export interface PincodeProps {
  pincode: string;
  office_name: string;
  pop_est: number | null;
}

// Reference layers change only when ingestion re-runs: cache them for the session.
const forever = { staleTime: Infinity, gcTime: Infinity } as const;

export function useStores() {
  return useQuery({
    queryKey: ["ref", "stores"],
    queryFn: () => api<FeatureCollection<Point, StoreProps>>("/ref/stores"),
    ...forever,
  });
}

export interface OpportunityCell {
  h3: string;
  score: number;
  pop: number;
  nearest_store_km: number;
}

export function useOpportunity(enabled: boolean) {
  return useQuery({
    queryKey: ["ref", "opportunity"],
    queryFn: () => api<OpportunityCell[]>("/ref/opportunity"),
    enabled,
    ...forever,
  });
}

export function usePincodeLayer() {
  return useQuery({
    queryKey: ["ref", "pincodes.geojson"],
    queryFn: () => api<FeatureCollection<MultiPolygon, PincodeProps>>("/ref/pincodes.geojson"),
    ...forever,
  });
}
