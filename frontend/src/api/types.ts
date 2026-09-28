export type Role = "BDM" | "BDE" | "SM" | "SE";

export interface User {
  id: string;
  username: string;
  name: string;
  role: Role;
  role_label: string;
  phone: string | null;
}

export interface Persona {
  username: string;
  name: string;
  role: Role;
  role_label: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}

export type StepStatus = "pending" | "running" | "done" | "failed" | "skipped";

export interface JobStep {
  name: string;
  label: string;
  status: StepStatus;
  started_at?: string;
  finished_at?: string;
  error?: string;
}

export type JobStatus = "queued" | "running" | "completed" | "partial" | "failed";

export interface Job {
  id: string;
  type: string;
  status: JobStatus;
  steps: JobStep[];
  error: string | null;
  attempts: number;
}
