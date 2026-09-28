import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Persona, TokenResponse } from "@/api/types";
import { useAuth } from "@/stores/auth";

export function usePersonas() {
  return useQuery({ queryKey: ["personas"], queryFn: () => api<Persona[]>("/auth/personas") });
}

/** Logs in as a seeded persona (demo mode). Clears cached data from the previous persona. */
export function useDemoLogin() {
  const qc = useQueryClient();
  const signIn = useAuth((s) => s.signIn);
  return useMutation({
    mutationFn: (username: string) =>
      api<TokenResponse>("/auth/demo-login", { body: { username } }),
    onSuccess: (res) => {
      qc.clear();
      signIn(res.access_token, res.user);
    },
  });
}
