import type { LucideIcon } from "lucide-react";
import {
  Building2,
  ClipboardList,
  FileBarChart,
  Inbox,
  KanbanSquare,
  ListChecks,
  Map,
  MapPin,
  PlusCircle,
} from "lucide-react";
import type { Role } from "@/api/types";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

/** Each persona gets a navigation shaped around their job. */
export const NAV: Record<Role, NavItem[]> = {
  BDM: [
    { to: "/bdm/explore", label: "Explore", icon: Map },
    { to: "/bdm/reports", label: "Reports", icon: FileBarChart },
    { to: "/bdm/pipeline", label: "Pipeline", icon: KanbanSquare },
    { to: "/bdm/studies", label: "Studies", icon: ClipboardList },
  ],
  BDE: [
    { to: "/bde/tasks", label: "My tasks", icon: MapPin },
    { to: "/bde/new", label: "Add property", icon: PlusCircle },
    { to: "/bde/properties", label: "My properties", icon: Building2 },
  ],
  SM: [
    { to: "/sm/inbox", label: "Requests", icon: Inbox },
    { to: "/sm/studies", label: "Studies", icon: ClipboardList },
  ],
  SE: [{ to: "/se/assignments", label: "Assignments", icon: ListChecks }],
};

export const HOME: Record<Role, string> = {
  BDM: "/bdm/explore",
  BDE: "/bde/tasks",
  SM: "/sm/inbox",
  SE: "/se/assignments",
};
