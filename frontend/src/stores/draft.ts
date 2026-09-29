import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { PropertyForm } from "@/api/properties";

export type Draft = Partial<PropertyForm> & { step?: number; savedAt?: string };

/** Drafts are per user: one browser is shared by every persona in the demo (and on a shared phone). */
export const draftKey = (userId: string, propertyId?: string) => `${userId}:${propertyId ?? "new"}`;

interface DraftState {
  drafts: Record<string, Draft>; // key: draftKey(user, "new" or the property id being edited)
  save: (key: string, d: Draft) => void;
  clear: (key: string) => void;
}

/** Field drafts live in localStorage so a reload, a dropped network or a phone call
 *  never loses a half-filled property. (Photos stay in memory until submit.) */
export const useDrafts = create<DraftState>()(
  persist(
    (set) => ({
      drafts: {},
      save: (key, d) =>
        set((s) => ({ drafts: { ...s.drafts, [key]: { ...s.drafts[key], ...d, savedAt: new Date().toISOString() } } })),
      clear: (key) =>
        set((s) => {
          const next = { ...s.drafts };
          delete next[key];
          return { drafts: next };
        }),
    }),
    { name: "sitescout-drafts" },
  ),
);
