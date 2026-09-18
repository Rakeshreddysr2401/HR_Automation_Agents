export type EscalationType =
  | "column_mapping"
  | "date_convention"
  | "enum_value"
  | "duplicate_suspected"
  | "rehire_suspected"
  | "validation_failed"
  | "hierarchy_orphan"
  | "hierarchy_cycle"
  | "push_rejected"
  | "batch_anomaly";

export interface Option {
  value: string;
  label: string;
  detail?: string;
}

export interface Escalation {
  id: string;
  run_id: string;
  subject: string;
  type: EscalationType;
  title: string;
  question: string;
  evidence: Record<string, any>;
  options: Option[];
  affected_records: string[];
  affected_count: number;
  status: "open" | "resolved" | "rejected";
  resolution: unknown;
  created_at: string;
}

export interface TargetRecord {
  key: string;
  fields: Record<string, any>;
  sources: string[];
  errors: string[];
  blocked_by: string[];
  push_status: string;
  push_detail: string;
  ready: boolean;
}

export interface AuditEntry {
  id: string;
  at: string;
  actor: "agent" | "human" | "system";
  action: string;
  entity: string;
  before: unknown;
  after: unknown;
  rationale: string;
  disposition: string | null;
}

export interface Summary {
  run_id?: string;
  columns?: number;
  columns_auto?: number;
  columns_flagged?: number;
  columns_ignored?: number;
  records?: number;
  records_ready?: number;
  records_blocked?: number;
  records_skipped?: number;
  escalations?: number;
  audit_entries?: number;
  breaker_tripped?: boolean;
  elapsed_seconds?: number;
  pushed?: number;
  push_failed?: number;
  push_rejected?: number;
}

export type Decision = string | boolean | { action: string; fields?: Record<string, string> };

export interface ModelStatus {
  enabled: boolean;
  embedding: { provider: string; model: string; base_url: string; reachable: boolean };
  reasoning: { provider: string; model: string; base_url: string; reachable: boolean };
}
